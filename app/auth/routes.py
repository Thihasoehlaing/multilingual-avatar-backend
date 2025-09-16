from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from uuid import uuid4

from app.deps import get_db, get_current_user
from app.users import crud as users_crud
from app.auth.password import hash_password, verify_password
from app.auth.jwt_handler import create_access_token
from app.utils.rate_limit import limiter
from app.utils.response import success
from app.utils.errors import AuthError, BadRequestError
from app.config import settings

router = APIRouter()

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)  # simple guard for demo
    full_name: str | None = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

def _normalize_email(email: str) -> str:
    return str(email).strip().lower()

@router.post("/signup")
@limiter.limit(f"{settings.RATE_AUTH_PER_MIN}/minute")
async def signup(request: Request, payload: SignupRequest, db = Depends(get_db)):
    email = _normalize_email(payload.email)
    if len(payload.password) < 6:  # explicit, readable check
        raise BadRequestError("Password too short (min 6)")

    existing = await users_crud.get_by_email(db, email)
    if existing:
        # Keep message generic to avoid account enumeration patterns
        raise BadRequestError("Email not available")

    user_id = str(uuid4())
    pwd_hash = hash_password(payload.password)
    await users_crud.insert_user(db, user_id, email, pwd_hash, full_name=payload.full_name)

    token = create_access_token(subject=user_id, extra_claims={"email": email})
    return success({"token": token})

@router.post("/login")
@limiter.limit(f"{settings.RATE_AUTH_PER_MIN*2}/minute")
async def login(request: Request, payload: LoginRequest, db = Depends(get_db)):
    email = _normalize_email(payload.email)
    user = await users_crud.get_by_email(db, email)
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        # Don’t reveal which part failed
        raise AuthError("Invalid credentials")

    token = create_access_token(subject=user["_id"], extra_claims={"email": email})
    # Return a small profile slice so the client can show a name immediately
    profile = {
        "user_id": user["_id"],
        "email": user["email"],
        "full_name": user.get("full_name"),
        "gender": user.get("gender"),
        "voice_pref": user.get("voice_pref"),
    }
    return success({"token": token, "profile": profile})

@router.get("/me")
async def me(request: Request, current_user = Depends(get_current_user)):
    return success({
        "user_id": current_user["_id"],
        "email": current_user["email"],
        "full_name": current_user.get("full_name"),
        "gender": current_user.get("gender"),
        "voice_pref": current_user.get("voice_pref"),
    })
