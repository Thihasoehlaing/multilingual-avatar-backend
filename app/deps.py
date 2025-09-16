from fastapi import Depends, Header, HTTPException, Request, status
from typing import Optional, Dict, Any

from app.auth.jwt_handler import decode_token

def get_db(request: Request):
    return request.app.state.db

async def get_current_user(
    authorization: Optional[str] = Header(None),
    db = Depends(get_db),
) -> Dict[str, Any]:
    """Extract user from Bearer token and fetch doc from DB."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = await db.users.find_one({"_id": user_id}, {"password_hash": 0})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user  # dict with _id, email, gender, voice_pref, etc.
