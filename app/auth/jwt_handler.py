from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import HTTPException, status
from jose import jwt, JWTError

from app.config import settings

ALGORITHM = "HS256"


def create_access_token(
    subject: str,
    expires_minutes: Optional[int] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a signed JWT.
    - subject: user_id (string UUID)
    - expires_minutes: overrides default if provided
    - extra_claims: optional additional claims (e.g., {"email": "..."} )
    """
    exp_minutes = expires_minutes or settings.JWT_EXPIRES_MINUTES
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=exp_minutes)).timestamp()),
        "iss": settings.APP_NAME,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT; raise 401 on failure."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
