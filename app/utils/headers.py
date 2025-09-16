from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request, call_next):
        resp: Response = await call_next(request)
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        # CSP mainly belongs on frontends; keep API narrow:
        resp.headers.setdefault("Permissions-Policy", "microphone=(), camera=()")
        return resp
