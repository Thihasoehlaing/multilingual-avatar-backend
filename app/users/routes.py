from fastapi import APIRouter, Depends, Request
from app.deps import get_db, get_current_user
from app.users.models import UserUpdate
from app.users import crud as users_crud

from app.utils.response import success
from app.utils.errors import BadRequestError
from app.utils.rate_limit import limiter
from app.config import settings

from app.utils.avatar import avatar_for_gender
from app.tts.services import is_voice_available

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", summary="Get my profile")
@limiter.limit(f"{settings.RATE_AUTH_PER_MIN*2}/minute")
async def get_me(
    request: Request,
    current_user = Depends(get_current_user),
):
    gender = current_user.get("gender")
    return success({
        "user_id": current_user["_id"],
        "email": current_user["email"],
        "full_name": current_user.get("full_name"),
        "gender": gender,
        "voice_pref": current_user.get("voice_pref"),
        "avatar": avatar_for_gender(gender),
    })


@router.put("/me", summary="Update my profile")
@limiter.limit(f"{settings.RATE_AUTH_PER_MIN}/minute")
async def update_me(
    request: Request,
    payload: UserUpdate,
    current_user = Depends(get_current_user),
    db = Depends(get_db),
):
    updates = {}

    # --- full_name ---
    if payload.full_name is not None:
        full_name = payload.full_name.strip()
        if len(full_name) == 0:
            raise BadRequestError("Full name cannot be empty")
        if len(full_name) > 100:
            raise BadRequestError("Full name too long")
        updates["full_name"] = full_name

    # --- gender (enum validated by Pydantic: male|female) ---
    if payload.gender is not None:
        updates["gender"] = payload.gender

    # --- voice_pref (validate against Polly voices available in this region) ---
    if payload.voice_pref is not None:
        vp = payload.voice_pref.strip()
        if not vp:
            raise BadRequestError("voice_pref cannot be empty")
        # If you want to constrain by a target language the user last chose,
        # pass lang=... here. For now, validate broadly in-region.
        if not is_voice_available(vp, lang=None):
            raise BadRequestError(f"Voice '{vp}' is not available in this region")
        updates["voice_pref"] = vp

    if not updates:
        raise BadRequestError("No changes provided")

    await users_crud.update_profile(db, current_user["_id"], updates)
    merged = {**current_user, **updates}
    gender = merged.get("gender")

    return success({
        "user_id": merged["_id"],
        "email": merged["email"],
        "full_name": merged.get("full_name"),
        "gender": gender,
        "voice_pref": merged.get("voice_pref"),
        "avatar": avatar_for_gender(gender),
    })
