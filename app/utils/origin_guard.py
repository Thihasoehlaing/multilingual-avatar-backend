from fastapi import Request, HTTPException, status
from app.config import settings

async def enforce_origin(request: Request):
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    allowed = [str(o) for o in settings.ALLOW_ORIGINS]
    if settings.APP_ENV != "dev" and origin and not any(origin.startswith(a) for a in allowed):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden origin")
