from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

async def create_session(db, session_id: str, user_id: str, payload: Dict[str, Any]) -> None:
    doc = {
        "_id": session_id,
        "user_id": user_id,
        "source_lang": payload["source_lang"],
        "target_lang": payload["target_lang"],
        "prosody": payload.get("prosody", {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
    }
    await db.sessions.insert_one(doc)

async def end_session(db, session_id: str) -> None:
    from datetime import datetime, timezone
    await db.sessions.update_one(
        {"_id": session_id},
        {"$set": {"ended_at": datetime.now(timezone.utc).isoformat()}}
    )

async def list_sessions_by_user(db, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    cursor = db.sessions.find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(length=limit)
