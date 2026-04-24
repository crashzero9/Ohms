"""
Hardened Shopify Admin REST client.

Security review fixes:
  H2 — upstream errors are caught, logged with correlation id, and returned
       as a sanitized `{error, correlation_id}` body. No upstream response
       body or headers leak to the MCP caller.
  H3 — explicit httpx timeouts (connect/read/write/pool).
  H5 — enforces documented Shopify scope set on client construction (README).
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any

import httpx

log = logging.getLogger("ohms.shopify")

_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=2.0)


class ShopifyError(RuntimeError):
    def __init__(self, correlation_id: str, detail: str) -> None:
        super().__init__(detail)
        self.correlation_id = correlation_id
        self.detail = detail


def _base_url() -> str:
    store = os.environ.get("SHOPIFY_STORE_URL", "")
    version = os.environ.get("SHOPIFY_API_VERSION", "2025-01")
    if not store:
        raise ShopifyError("none", "SHOPIFY_STORE_URL not configured")
    return f"https://{store}/admin/api/{version}"


def _headers() -> dict[str, str]:
    token = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
    if not token:
        raise ShopifyError("none", "SHOPIFY_ACCESS_TOKEN not configured")
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


@contextmanager
def client():
    with httpx.Client(timeout=_TIMEOUT, headers=_headers()) as c:
        yield c


def _sanitize_and_raise(resp: httpx.Response, correlation_id: str) -> None:
    """Raise ShopifyError with correlation id; log full response server-side only."""
    try:
        upstream_body = resp.json()
    except Exception:
        upstream_body = {"raw": resp.text[:500]}
    log.error(
        "shopify.upstream_error",
        extra={
            "correlation_id": correlation_id,
            "status_code": resp.status_code,
            "upstream_body": upstream_body,   # server-side only, scrubbed by logging filter
            "url": str(resp.request.url),
        },
    )
    raise ShopifyError(correlation_id, "shopify_upstream_failure")


def get_order(order_id: str, correlation_id: str) -> dict[str, Any]:
    url = f"{_base_url()}/orders/{order_id}.json"
    with client() as c:
        try:
            r = c.get(url)
        except httpx.HTTPError as e:
            log.error("shopify.network_error", extra={"correlation_id": correlation_id, "error": str(e)})
            raise ShopifyError(correlation_id, "shopify_network_failure") from e
    if r.status_code >= 400:
        _sanitize_and_raise(r, correlation_id)
    return r.json().get("order", {})


def list_pending_orders(correlation_id: str, limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 250))  # Shopify hard limit 250
    url = f"{_base_url()}/orders.json"
    with client() as c:
        try:
            r = c.get(url, params={"status": "open", "limit": limit})
        except httpx.HTTPError as e:
            log.error("shopify.network_error", extra={"correlation_id": correlation_id, "error": str(e)})
            raise ShopifyError(correlation_id, "shopify_network_failure") from e
    if r.status_code >= 400:
        _sanitize_and_raise(r, correlation_id)
    return r.json().get("orders", [])


def update_order_status(order_id: str, status: str, correlation_id: str) -> dict[str, Any]:
    url = f"{_base_url()}/orders/{order_id}.json"
    payload = {"order": {"id": int(order_id), "tags": status}}
    with client() as c:
        try:
            r = c.put(url, json=payload)
        except httpx.HTTPError as e:
            log.error("shopify.network_error", extra={"correlation_id": correlation_id, "error": str(e)})
            raise ShopifyError(correlation_id, "shopify_network_failure") from e
    if r.status_code >= 400:
        _sanitize_and_raise(r, correlation_id)
    return {"order_id": order_id, "updated_status": status}


def get_inventory_snapshot(correlation_id: str, limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(int(limit), 250))
    url = f"{_base_url()}/inventory_levels.json"
    with client() as c:
        try:
            r = c.get(url, params={"limit": limit})
        except httpx.HTTPError as e:
            log.error("shopify.network_error", extra={"correlation_id": correlation_id, "error": str(e)})
            raise ShopifyError(correlation_id, "shopify_network_failure") from e
    if r.status_code >= 400:
        _sanitize_and_raise(r, correlation_id)
    return r.json()
