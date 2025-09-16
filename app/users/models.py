from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal

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
    voice_pref: Optional[str] = None

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    gender: Optional[Gender] = None
    voice_pref: Optional[str] = None
