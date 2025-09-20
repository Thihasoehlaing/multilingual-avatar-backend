from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
from app.config import settings

_client: Optional[AsyncIOMotorClient] = None

def _build_mongo_uri() -> str:
    # e.g. mongodb://user:pass@127.0.0.1:27017/ai_avatar?authSource=admin
    user = settings.MONGO_USERNAME
    pwd  = settings.MONGO_PASSWORD
    host = settings.MONGO_HOST
    port = settings.MONGO_PORT
    db   = settings.MONGO_DATABASE
    auth = settings.MONGO_AUTH_SOURCE
    return f"{settings.MONGO_CONNECTION}://{user}:{pwd}@{host}:{port}/{db}?authSource={auth}"

async def connect_to_mongo(app) -> None:
    """Create client and attach DB handle to app.state.db."""
    global _client
    uri = _build_mongo_uri()
    _client = AsyncIOMotorClient(uri)
    app.state.db = _client[settings.MONGO_DATABASE]

async def close_mongo_connection(app) -> None:
    global _client
    if _client:
        _client.close()
        _client = None
        app.state.db = None

def get_db_from_app(app) -> AsyncIOMotorDatabase:
    return app.state.db
