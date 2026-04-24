"""
Minimal health endpoint.

Security review fix: M1 — constrain /health to exact path, return minimal JSON.
No version, git sha, or environment info leaked to unauthenticated callers.
"""

from starlette.responses import JSONResponse


async def health_endpoint(request):
    return JSONResponse({"ok": True}, status_code=200)
