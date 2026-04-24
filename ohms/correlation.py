"""
Correlation-ID middleware.

Attaches a `correlation_id` to every request's state and echoes it on the
response as `X-OHMS-Request-ID`. All tool + shopify-client logs reference it
via `log.info(..., extra={"correlation_id": ...})` so any upstream failure
is traceable from the caller's side.
"""

from __future__ import annotations

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("ohms.correlation")

HEADER_IN = "X-OHMS-Request-ID"
HEADER_OUT = "X-OHMS-Request-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        incoming = request.headers.get(HEADER_IN)
        cid = incoming if incoming and len(incoming) <= 128 else uuid.uuid4().hex
        request.state.correlation_id = cid
        log.info(
            "request.start",
            extra={
                "correlation_id": cid,
                "path": request.url.path,
                "method": request.method,
                "client_ip": request.client.host if request.client else "unknown",
                # Do NOT log Authorization header; logging_setup scrubs it anyway.
            },
        )
        response = await call_next(request)
        response.headers[HEADER_OUT] = cid
        log.info(
            "request.end",
            extra={
                "correlation_id": cid,
                "status_code": response.status_code,
            },
        )
        return response
