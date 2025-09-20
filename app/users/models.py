from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal, Dict

# Only two avatars in your app
Gender = Literal["male", "female"]

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserPublic(BaseModel):
    user_id: str = Field(alias="_id")
    email: EmailStr
    full_name: Optional[str] = None
    gender: Optional[Gender] = None
    # Per-language voice overrides: { "en-US": "Matthew", "zh-CN": "Zhiyu" }
    voice_overrides: Dict[str, str] = {}

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    gender: Optional[Gender] = None
    # Upsert/replace the whole dict (simplest). If you want granular patching, add another route.
    voice_overrides: Optional[Dict[str, str]] = None
