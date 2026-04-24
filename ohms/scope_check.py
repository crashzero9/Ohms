"""
Shopify scope assertion — runs at startup (Phase 3 security review C-item).

Calls Shopify's `/admin/oauth/access_scopes.json` and refuses to start if
the token's granted scopes are anything other than the documented set:
    read_orders, write_orders, read_inventory

Fail-closed: a mis-minted token with `write_customers` or `read_all_orders`
must not be allowed to run.

Enabled only when SHOPIFY_STORE_URL + SHOPIFY_ACCESS_TOKEN are set (Phase 3
onwards). Phase 1 scaffold tests don't need Shopify config, so this is a
no-op during local boot without Shopify env vars.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

import httpx

log = logging.getLogger("ohms.scope_check")

REQUIRED_SCOPES = frozenset({"read_orders", "write_orders", "read_inventory"})


class ScopeViolation(RuntimeError):
    pass


def assert_shopify_scopes(required: Iterable[str] = REQUIRED_SCOPES) -> None:
    store = os.environ.get("SHOPIFY_STORE_URL", "")
    token = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
    if not store or not token:
        log.info("scope_check.skipped", extra={"reason": "shopify_env_not_configured"})
        return
    version = os.environ.get("SHOPIFY_API_VERSION", "2025-01")
    url = f"https://{store}/admin/api/{version}/oauth/access_scopes.json"
    headers = {
        "X-Shopify-Access-Token": token,
        "Accept": "application/json",
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=3.0, read=5.0)) as c:
            r = c.get(url, headers=headers)
    except httpx.HTTPError as e:
        log.error("scope_check.network_error", extra={"error": str(e)})
        raise ScopeViolation("unable to confirm shopify scopes") from e

    if r.status_code != 200:
        log.error("scope_check.http_error", extra={"status_code": r.status_code})
        raise ScopeViolation(f"shopify returned {r.status_code} on scope check")

    granted = {item.get("handle") for item in r.json().get("access_scopes", [])}
    required_set = set(required)

    extra = granted - required_set
    missing = required_set - granted
    if extra or missing:
        log.error(
            "scope_check.mismatch",
            extra={"granted": sorted(granted), "required": sorted(required_set),
                   "extra": sorted(extra), "missing": sorted(missing)},
        )
        raise ScopeViolation(
            f"shopify scope mismatch — extra={sorted(extra)} missing={sorted(missing)}"
        )

    log.info("scope_check.ok", extra={"granted": sorted(granted)})
