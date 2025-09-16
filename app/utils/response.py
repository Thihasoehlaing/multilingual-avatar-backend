from fastapi.responses import JSONResponse
from typing import Any

def success(data: Any = None, message: str = "ok", status_code: int = 200):
    return JSONResponse(status_code=status_code, content={"ok": True, "message": message, "data": data})

def error(message: str = "error", status_code: int = 400, details: Any = None):
    body = {"ok": False, "error": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body)
