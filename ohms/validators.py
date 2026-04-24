"""
Input validators for OHMS tool boundaries.

Security review fix: C4 — order_id URL injection.

Every value that flows into an URL path segment or query parameter passes
through a validator here. Tools call `validate_order_id()` *before* any
httpx call is issued.
"""

from __future__ import annotations

import ipaddress
import re

# Shopify order IDs are 64-bit integers serialized as digit strings.
# Real observed range: 10-14 digits, allow 6-20 for headroom.
_ORDER_ID_RE = re.compile(r"^\d{6,20}$")

# Shopify status tags — constrained vocabulary for update_order_status.
_ALLOWED_STATUSES: frozenset[str] = frozenset({
    "pending", "preparing", "ready_for_pickup", "out_for_delivery",
    "delivered", "cancelled", "refunded", "issue_flagged",
})

# Printer IP must be on an RFC1918 private range. No public IPs allowed.
# Security review fix: M2 — prevent SSRF via misconfigured PRINTER_IP.
_ALLOWED_PRINTER_CIDRS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]


class ValidationError(ValueError):
    """Raised when an input fails validation at a tool boundary."""


def validate_order_id(order_id: str) -> str:
    if not isinstance(order_id, str):
        raise ValidationError("order_id must be a string")
    if not _ORDER_ID_RE.fullmatch(order_id):
        raise ValidationError("order_id must be 6-20 digits")
    return order_id


def validate_status(status: str) -> str:
    if status not in _ALLOWED_STATUSES:
        raise ValidationError(
            f"status must be one of: {sorted(_ALLOWED_STATUSES)}"
        )
    return status


def validate_printer_ip(ip: str) -> str:
    try:
        addr = ipaddress.ip_address(ip)
    except (ValueError, TypeError) as e:
        raise ValidationError(f"printer_ip is not a valid IP: {e}") from e
    for net in _ALLOWED_PRINTER_CIDRS:
        if addr in net:
            return str(addr)
    raise ValidationError(
        "printer_ip must be on a private LAN (RFC1918)"
    )
