from fastapi import APIRouter, Depends, Request

from app.config import settings
from app.deps import get_current_user, get_db
from app.users import crud as users_crud
from app.users.models import UserUpdate
from app.utils.avatar import avatar_for_gender
from app.utils.errors import BadRequestError
from app.utils.rate_limit import limiter
from app.utils.response import success

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
@limiter.limit(f"{settings.RATE_AUTH_PER_MIN*2}/minute")
async def get_me(request: Request, current_user=Depends(get_current_user)):
    gender = current_user.get("gender")
    return success({
        "user_id": current_user["_id"],
        "email": current_user["email"],
        "full_name": current_user.get("full_name"),
        "gender": gender,
        "voice_overrides": current_user.get("voice_overrides", {}),
        "avatar": avatar_for_gender(gender),
    })


@router.put("/me")
@limiter.limit(f"{settings.RATE_AUTH_PER_MIN}/minute")
async def update_me(
    request: Request,
    payload: UserUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    updates = {}

    # full_name
    if payload.full_name is not None:
        full_name = payload.full_name.strip()
        if len(full_name) == 0:
            raise BadRequestError("Full name cannot be empty")
        if len(full_name) > 100:
            raise BadRequestError("Full name too long")
        updates["full_name"] = full_name

    # gender
    if payload.gender is not None:
        updates["gender"] = payload.gender

    # per-language voice overrides
    if payload.voice_overrides is not None:
        if not isinstance(payload.voice_overrides, dict):
            raise BadRequestError("voice_overrides must be an object map of {lang: VoiceId}")
        cleaned = {str(k): str(v).strip() for k, v in payload.voice_overrides.items() if str(v).strip()}
        updates["voice_overrides"] = cleaned

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
        "voice_overrides": merged.get("voice_overrides", {}),
        "avatar": avatar_for_gender(gender),
    })
