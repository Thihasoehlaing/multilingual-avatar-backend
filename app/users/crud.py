from typing import Optional, Dict, Any
from datetime import datetime, timezone

async def get_by_email(db, email: str) -> Optional[Dict[str, Any]]:
    return await db.users.find_one({"email": email})

async def get_by_id(db, user_id: str) -> Optional[Dict[str, Any]]:
    return await db.users.find_one({"_id": user_id})

async def insert_user(db, user_id: str, email: str, password_hash: str, full_name: Optional[str] = None) -> None:  # CHANGED
    doc = {
        "_id": user_id,
        "email": email,
        "password_hash": password_hash,
        "full_name": full_name,
        "gender": None,
        "voice_pref": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(doc)

async def update_profile(db, user_id: str, updates: Dict[str, Any]) -> None:
    await db.users.update_one({"_id": user_id}, {"$set": updates})
