from fastapi import APIRouter, Depends, Query, Request
from app.deps import get_db, get_current_user
from app.users.models import UserUpdate
from app.users import crud as users_crud

from app.utils.response import success
from app.utils.errors import BadRequestError
from app.utils.rate_limit import limiter
from app.config import settings

router = APIRouter()

@router.get("/me", summary="Get my profile")
@limiter.limit(f"{settings.RATE_AUTH_PER_MIN*2}/minute")
async def get_me(request: Request, current_user = Depends(get_current_user)):
    return success({
        "user_id": current_user["_id"],
        "email": current_user["email"],
        "full_name": current_user.get("full_name"),
        "gender": current_user.get("gender"),
        "voice_pref": current_user.get("voice_pref"),
    })

@router.put("/me", summary="Update my profile")
@limiter.limit(f"{settings.RATE_AUTH_PER_MIN}/minute")
async def update_me(request: Request,                                             # <-- add request
    payload: UserUpdate,
    current_user = Depends(get_current_user),
    db = Depends(get_db),
):
    updates = {}

    # Basic normalization / validation
    if payload.full_name is not None:
        full_name = payload.full_name.strip()
        if len(full_name) == 0:
            raise BadRequestError("Full name cannot be empty")
        # (Optional) cap length to avoid silly payloads
        if len(full_name) > 100:
            raise BadRequestError("Full name too long")
        updates["full_name"] = full_name

    if payload.gender is not None:
        # Gender enum is already validated by Pydantic (male|female)
        updates["gender"] = payload.gender

    if payload.voice_pref is not None:
        # You could validate against a known set of Polly voices here
        updates["voice_pref"] = payload.voice_pref

    if not updates:
        raise BadRequestError("No changes provided")

    await users_crud.update_profile(db, current_user["_id"], updates)
    merged = {**current_user, **updates}

    return success({
        "user_id": merged["_id"],
        "email": merged["email"],
        "full_name": merged.get("full_name"),
        "gender": merged.get("gender"),
        "voice_pref": merged.get("voice_pref"),
    })
