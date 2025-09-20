from typing import Optional, Dict, Any
from datetime import datetime, timezone


async def get_by_email(db, email: str) -> Optional[Dict[str, Any]]:
    return await db.users.find_one({"email": email})


async def get_by_id(db, user_id: str) -> Optional[Dict[str, Any]]:
    # _id is stored as a string in your insert; no ObjectId conversion needed
    return await db.users.find_one({"_id": user_id})


async def insert_user(
    db,
    user_id: str,
    email: str,
    password_hash: str,
    full_name: Optional[str] = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    doc: Dict[str, Any] = {
        "_id": user_id,
        "email": email,
        "password_hash": password_hash,
        "full_name": full_name,
        "gender": None,
        # Per-language Polly voices; keep empty dict by default
        "voice_overrides": {},
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(doc)


async def update_profile(db, user_id: str, updates: Dict[str, Any]) -> None:
    # Ensure updated_at is always refreshed
    updates = {**updates, "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.users.update_one({"_id": user_id}, {"$set": updates})
