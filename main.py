"""
OHMS — Flauraly Order Hub Management System
Entry point for the Replit Reserved VM deployment.

This file assembles the FastMCP server, the hardened Starlette middleware stack,
and the ASGI application served by uvicorn.

All tool implementations live in ohms/tools.py.
All auth / validation / logging helpers live in their respective ohms/ modules.

Phase 1 hardening (addresses security review findings C1-C4, H1-H6, M1-M5):
  - hmac.compare_digest Bearer comparison          [C1]
  - Scoped tokens: READ vs WRITE                   [C2]
  - DoorDash browser tool isolated + schema-checked[C3]
  - order_id regex validation at tool boundary    [C4]
  - slowapi rate limiting per (ip, token prefix)   [H1]
  - sanitized upstream error responses             [H2]
  - explicit httpx timeouts + retries              [H3]
  - redacting log filter                           [H4]
  - Shopify scope documented in README            [H5]
  - TrustedHost + CORS closed                     [H6]
  - /health returns minimal JSON                   [M1]
  - PRINTER_IP CIDR allow-list                     [M2]
  - correlation-id middleware                      [M3]
  - pydantic return types on tools                 [M4]
  - secret rotation runbook in docs/              [M5]
"""

from __future__ import annotations

import os
import logging

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.routing import Mount, Route

from ohms import tools  # registers tools on import
from ohms.auth import BearerAuthMiddleware
from ohms.correlation import CorrelationIdMiddleware
from ohms.health import health_endpoint
from ohms.logging_setup import configure_logging
from ohms.rate_limit import build_rate_limit_middleware
from ohms.scope_check import assert_shopify_scopes, ScopeViolation

# --- Logging setup (first, so subsequent imports log correctly) -------------
configure_logging()
log = logging.getLogger("ohms.main")

# --- Shopify scope assertion (Phase 3 C-item, fail-closed) ------------------
# If SHOPIFY_STORE_URL + SHOPIFY_ACCESS_TOKEN are set, the token must grant
# *exactly* {read_orders, write_orders, read_inventory} — no more, no less.
# A mis-minted token refuses to boot.
try:
    assert_shopify_scopes()
except ScopeViolation as exc:
    log.critical("startup.scope_violation", extra={"detail": str(exc)})
    raise SystemExit(
        "OHMS refusing to start — Shopify token scope mismatch. "
        "Rotate the token with the documented scope set."
    ) from exc

# --- FastMCP server ---------------------------------------------------------
# Kwarg compatibility: different mcp SDK versions accept different params.
#   - 'description' was removed in favour of 'instructions' in some builds.
#   - 'stateless_http' is a newer setting; older SDKs ignore or reject it.
# We try the richest constructor first and fall back gracefully.
_mcp_kwargs: dict = {}
try:
    FastMCP("_probe", stateless_http=True)   # test if kwarg is accepted
    _mcp_kwargs["stateless_http"] = True
except TypeError:
    pass  # older SDK — stateless_http not supported; server runs stateful

mcp = FastMCP("OHMS", **_mcp_kwargs)
mcp.settings.host = "0.0.0.0"
mcp.settings.port = int(os.environ.get("PORT", 8080))

# Bind tool module to this FastMCP instance. tools.register() walks the module
# and attaches each @tool-decorated function plus its required scope.
tools.register(mcp)

# --- Middleware stack -------------------------------------------------------
# Order matters: TrustedHost -> CorrelationId -> RateLimit -> BearerAuth.
allowed_host = os.environ.get("OHMS_PUBLIC_HOST", "*")  # override in Replit Secrets once deployed
rate_limit_mw = build_rate_limit_middleware()

middleware = [
    Middleware(TrustedHostMiddleware, allowed_hosts=[allowed_host]) if allowed_host != "*" else None,
    Middleware(CORSMiddleware, allow_origins=[], allow_credentials=False, allow_methods=[], allow_headers=[]),
    Middleware(CorrelationIdMiddleware),
    rate_limit_mw,
    Middleware(BearerAuthMiddleware),
]
middleware = [m for m in middleware if m is not None]

# --- App assembly -----------------------------------------------------------
# FastMCP exposes two transports via streamable_http_app() and sse_app().
# Both return Starlette apps with INTERNAL path routing:
#   streamable_http_app() → handles POST /mcp  (Streamable HTTP, MCP 2025-11-05)
#   sse_app()             → handles GET /sse + POST /messages  (SSE legacy)
#
# CRITICAL: Do NOT use Mount("/mcp", app=streamable_app) — Starlette strips
# the "/mcp" prefix, so FastMCP's inner app receives "/" and returns 404
# because its internal route is "/mcp", not "/".
#
# Fix: Use a single Mount("/") dispatcher that preserves the full path, letting
# each FastMCP app see /mcp or /sse as it expects.


class _MCPTransportDispatcher:
    """Routes /mcp* to Streamable HTTP app, /sse* and /messages* to SSE app.

    Mounted at "/" so both inner apps receive the FULL unstripped path and
    can match their internal routes (/mcp and /sse respectively).
    """

    def __init__(self, streamable, sse):
        self.streamable = streamable
        self.sse = sse

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if path.startswith("/sse") or path.startswith("/messages"):
            await self.sse(scope, receive, send)
        else:
            await self.streamable(scope, receive, send)


try:
    streamable_app = mcp.streamable_http_app()
    sse_app = mcp.sse_app()
    mcp_routes = [Mount("/", app=_MCPTransportDispatcher(streamable_app, sse_app))]
except AttributeError:
    # Older/combined FastMCP: one ASGI app serves both endpoints internally.
    combined = mcp.get_asgi_app() if hasattr(mcp, "get_asgi_app") else mcp.sse_app()
    mcp_routes = [Mount("/", app=combined)]

app = Starlette(
    routes=[
        Route("/health", health_endpoint, methods=["GET"]),
        *mcp_routes,
    ],
    middleware=middleware,
)

if __name__ == "__main__":
    import uvicorn

    log.info(
        "OHMS starting",
        extra={
            "host": mcp.settings.host,
            "port": mcp.settings.port,
            "trusted_host": allowed_host,
            "tool_count": len(tools.REGISTERED),
        },
    )
    # access_log disabled — our CorrelationIdMiddleware emits structured logs
    # with PII/secret scrubbing (see ohms/logging_setup.py).
    uvicorn.run(
        app,
        host=mcp.settings.host,
        port=mcp.settings.port,
        access_log=False,
        log_config=None,  # we installed our own dictConfig
    )
