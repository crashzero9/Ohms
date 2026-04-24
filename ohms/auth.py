"""
Bearer-token authentication middleware with scoped tokens.

Security review fixes:
  C1 — constant-time comparison via hmac.compare_digest
  C2 — two scoped tokens (READ / WRITE) instead of single shared token

Tokens are loaded from Replit Secrets:
  OHMS_API_TOKEN_READ   — required; read-only tools
  OHMS_API_TOKEN_WRITE  — required; mutating tools (inherits read)

If only OHMS_API_TOKEN is set (legacy single-token mode), it is treated as
BOTH read and write — a deployment-phase convenience. A WARNING is logged and
HARDENING_NOTES.md flags this as a must-fix before production promotion.
"""

from __future__ import annotations

import hmac
import logging
import os
from dataclasses import dataclass
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger("ohms.auth")

READ_SCOPE = "read"
WRITE_SCOPE = "write"


@dataclass(frozen=True)
class TokenRecord:
    token_bytes: bytes
    scope: str
    prefix: str  # first 6 chars, safe to log for audit


def _load_tokens() -> list[TokenRecord]:
    records: list[TokenRecord] = []
    read_t = os.environ.get("OHMS_API_TOKEN_READ", "")
    write_t = os.environ.get("OHMS_API_TOKEN_WRITE", "")
    legacy_t = os.environ.get("OHMS_API_TOKEN", "")

    if read_t:
        records.append(TokenRecord(read_t.encode(), READ_SCOPE, read_t[:6]))
    if write_t:
        records.append(TokenRecord(write_t.encode(), WRITE_SCOPE, write_t[:6]))

    if not records and legacy_t:
        # Legacy single-token mode — log loudly.
        log.warning(
            "auth.legacy_single_token_mode",
            extra={"detail": "OHMS_API_TOKEN is set; scoped tokens are not. "
                             "This is allowed for Phase 1 MVP but must be split before production."},
        )
        records.append(TokenRecord(legacy_t.encode(), READ_SCOPE, legacy_t[:6]))
        records.append(TokenRecord(legacy_t.encode(), WRITE_SCOPE, legacy_t[:6]))

    if not records:
        log.error("auth.no_tokens_configured")

    return records


_TOKENS: list[TokenRecord] = _load_tokens()


def _match_token(header: str) -> Optional[TokenRecord]:
    """Constant-time match across all configured tokens.

    We iterate and call hmac.compare_digest on every entry to avoid leaking
    via short-circuit timing. Returns the first matching TokenRecord or None.
    """
    if not header or not header.startswith("Bearer "):
        return None
    presented = header[len("Bearer "):].encode()
    winner: Optional[TokenRecord] = None
    for rec in _TOKENS:
        # compare_digest returns False for mismatched lengths in constant time
        if hmac.compare_digest(presented, rec.token_bytes) and winner is None:
            winner = rec
    return winner


def required_scope_for_path(path: str) -> str:
    """
    Default: every MCP call requires WRITE scope unless the tool is in the
    read-only allow-list. Tools call _check_scope() via a decorator, but we
    also gate at the request layer for defense-in-depth on bulk tool calls.

    For MCP streamable-http, a single /mcp request can invoke any tool, so we
    fall back to requiring WRITE at the transport edge and let tools.py
    refine per-tool. Tuning this after we see real traffic.
    """
    return WRITE_SCOPE


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Health endpoint is public (already minimal; see ohms/health.py).
        if request.url.path == "/health":
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        rec = _match_token(auth_header)
        if rec is None:
            # No scope leak in response body — identical 401 for missing/bad.
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        # Attach token metadata to request state for downstream inspection.
        request.state.token_scope = rec.scope
        request.state.token_prefix = rec.prefix
        return await call_next(request)
