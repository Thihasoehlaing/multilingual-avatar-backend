from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.config import settings
from app.db.mongo import connect_to_mongo, close_mongo_connection
from app.db.indexes import ensure_indexes

# Rate limiting
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from app.utils.rate_limit import limiter

# Security headers + logging / errors
from app.utils.headers import SecurityHeadersMiddleware
from app.utils.logging import logger, request_id_ctx
from app.utils.errors import (
    handle_http_exception,
    handle_validation_error,
    handle_rate_limit,
    handle_unhandled,
)
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException

# Routers
from app.auth.routes import router as auth_router
from app.users.routes import router as users_router
from app.sessions.routes import router as sessions_router
from app.tts.routes import router as tts_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ----- Middleware -----
    # Host allowlist
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=(
            settings.TRUSTED_HOSTS + ["*"] if settings.APP_ENV == "dev" else settings.TRUSTED_HOSTS
        ),
    )

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # GZip large responses (e.g., viseme arrays)
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # Rate limiting
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    # CORS (keep strict; expand when you host the frontend)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(o) for o in settings.ALLOW_ORIGINS],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Per-request id for logging correlation
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        import uuid
        token = request_id_ctx.set(str(uuid.uuid4())[:8])
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-Id"] = request_id_ctx.get() or "-"
        return response

    # ----- Exception Handlers (unify JSON error shapes) -----
    app.add_exception_handler(HTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(RateLimitExceeded, handle_rate_limit)
    app.add_exception_handler(Exception, handle_unhandled)

    # ----- Lifecycle: DB connect / indexes / close -----
    @app.on_event("startup")
    async def _startup():
        await connect_to_mongo(app)
        await ensure_indexes(app.state.db)
        logger.info("Startup complete")

    @app.on_event("shutdown")
    async def _shutdown():
        await close_mongo_connection(app)
        logger.info("Shutdown complete")

    # ----- Health check -----
    @app.get("/healthz", tags=["system"])
    async def healthz():
        db = getattr(app.state, "db", None)
        mongo_ok = False
        if db is not None:
            try:
                await db.command("ping")
                mongo_ok = True
            except Exception:
                mongo_ok = False

        return {
            "status": "ok" if mongo_ok else "degraded",
            "db": mongo_ok,
            "app": settings.APP_NAME,
            "env": settings.APP_ENV,
            "version": app.version,
        }

    # ----- Routers -----
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(users_router, prefix="/users", tags=["users"])
    app.include_router(sessions_router, prefix="/sessions", tags=["sessions"])
    app.include_router(tts_router, prefix="/tts", tags=["tts"])

    return app


app = create_app()
