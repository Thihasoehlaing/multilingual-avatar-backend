from motor.motor_asyncio import AsyncIOMotorDatabase

async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    # Users: unique email
    await db.users.create_index("email", unique=True, name="uniq_email")

    # Sessions: by user and created_at (for quick listing)
    await db.sessions.create_index([("user_id", 1), ("created_at", -1)], name="user_created_idx")
