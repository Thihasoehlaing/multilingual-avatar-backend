from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette import status
from slowapi.errors import RateLimitExceeded

from app.utils.logging import logger

# Custom semantic errors (optional, use where clearer than HTTPException)
class AuthError(HTTPException):
    def __init__(self, detail="Unauthorized"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

class NotFoundError(HTTPException):
    def __init__(self, detail="Not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class BadRequestError(HTTPException):
    def __init__(self, detail="Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

# ---- Exception handlers (register these in main.py) ----
async def handle_http_exception(request: Request, exc: HTTPException):
    logger.warning(f"HTTPException {exc.status_code}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "error": exc.detail},
    )

async def handle_validation_error(request: Request, exc: RequestValidationError | ValidationError):
    logger.warning("ValidationError")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"ok": False, "error": "validation_error", "details": exc.errors()},
    )

async def handle_rate_limit(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"ok": False, "error": "rate_limited"})

async def handle_unhandled(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {type(exc).__name__}", exc_info=True)
    return JSONResponse(status_code=500, content={"ok": False, "error": "internal_error"})
