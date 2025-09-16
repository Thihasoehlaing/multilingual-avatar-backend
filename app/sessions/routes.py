from fastapi import APIRouter, Depends, Query, Request
from uuid import uuid4

from app.deps import get_db, get_current_user
from app.sessions.models import SessionCreate
from app.sessions import crud as sessions_crud

from app.utils.response import success
from app.utils.errors import NotFoundError, BadRequestError
from app.utils.rate_limit import limiter
from app.config import settings

router = APIRouter()


@router.post("", summary="Start a session")
@limiter.limit(f"{settings.RATE_AUTH_PER_MIN}/minute")  # light guard; tune if needed
async def start_session(
    request: Request,
    payload: SessionCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db),
):
    # payload already validated by Pydantic (source_lang/target_lang enums)
    sid = str(uuid4())
    await sessions_crud.create_session(db, sid, current_user["_id"], payload.model_dump())
    return success({"session_id": sid})


@router.post("/{session_id}/end", summary="End a session")
@limiter.limit(f"{settings.RATE_AUTH_PER_MIN}/minute")
async def end_session(
    request: Request,
    session_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db),
):
    # Ensure session belongs to the user
    sess = await db.sessions.find_one({"_id": session_id, "user_id": current_user["_id"]})
    if not sess:
        raise NotFoundError("Session not found")
    if sess.get("ended_at"):
        raise BadRequestError("Session already ended")
    await sessions_crud.end_session(db, session_id)
    return success()


@router.get("", summary="List recent sessions")
@limiter.limit(f"{settings.RATE_AUTH_PER_MIN*2}/minute")
async def list_sessions(
    request: Request,
    current_user = Depends(get_current_user),
    db = Depends(get_db),
    limit: int = Query(10, ge=1, le=50, description="Number of recent sessions to return (1-50)"),
):
    rows = await sessions_crud.list_sessions_by_user(db, current_user["_id"], limit=limit)
    return success(rows)
