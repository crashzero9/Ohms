"""
Rate-limit middleware (Phase 1 — in-memory token bucket).

Security review fix: H1 — no rate limiting on a public MCP endpoint.

Uses slowapi as an optional dependency. If slowapi is not installed we fall
back to a lightweight in-process bucket so the server still throttles by
default. For Phase 1 the in-process bucket is sufficient — a single-node
Reserved VM has a single process. Upgrade path: Redis-backed slowapi limiter
when we move to multi-node.

Default limits:
  - 60 req/min per (client_ip, token_prefix)
  - 10 req/min for write-scope calls (enforced in tools.py per-tool)

Override via env:
  OHMS_RATE_LIMIT_PER_MIN      (default 60)
  OHMS_RATE_LIMIT_WRITE_PER_MIN (default 10)
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from typing import Deque

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

log = logging.getLogger("ohms.rate_limit")

_WINDOW_SECONDS = 60
_DEFAULT_LIMIT = int(os.environ.get("OHMS_RATE_LIMIT_PER_MIN", "60"))


class _Bucket:
    __slots__ = ("stamps",)

    def __init__(self) -> None:
        self.stamps: Deque[float] = deque()

    def allow(self, now: float, limit: int, window: float = _WINDOW_SECONDS) -> bool:
        cutoff = now - window
        while self.stamps and self.stamps[0] < cutoff:
            self.stamps.popleft()
        if len(self.stamps) >= limit:
            return False
        self.stamps.append(now)
        return True


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit_per_min: int = _DEFAULT_LIMIT) -> None:
        super().__init__(app)
        self.limit = limit_per_min
        self._buckets: dict[tuple[str, str], _Bucket] = defaultdict(_Bucket)

    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        token_prefix = getattr(request.state, "token_prefix", "anon")
        key = (client_ip, token_prefix)
        if not self._buckets[key].allow(time.monotonic(), self.limit):
            log.warning(
                "rate_limit.exceeded",
                extra={"client_ip": client_ip, "token_prefix": token_prefix, "limit": self.limit},
            )
            return JSONResponse(
                {"error": "rate_limited", "retry_after_seconds": _WINDOW_SECONDS},
                status_code=429,
                headers={"Retry-After": str(_WINDOW_SECONDS)},
            )
        return await call_next(request)


def build_rate_limit_middleware() -> Middleware:
    return Middleware(InMemoryRateLimitMiddleware, limit_per_min=_DEFAULT_LIMIT)
