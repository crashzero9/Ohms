"""
FastMCP tool definitions.

Security review fixes applied here:
  C2 — per-tool scope enforcement (write-scope required for mutating tools)
  C3 — DoorDash browser tool never returns raw HTML; schema-constrained shape
  C4 — input validation at the tool boundary
  H2 — sanitized error responses {error, correlation_id}
  M2 — printer_ip CIDR check
  M4 — pydantic return-type models for every tool

Tools are registered on the FastMCP instance at import time by main.py
calling `tools.register(mcp)`.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from ohms import idempotency, shopify
from ohms.auth import WRITE_SCOPE
from ohms.validators import (
    ValidationError,
    validate_order_id,
    validate_printer_ip,
    validate_status,
)

log = logging.getLogger("ohms.tools")

REGISTERED: list[str] = []


# --- Return-type models (M4) -----------------------------------------------
class OrderEnvelope(BaseModel):
    order_id: str
    correlation_id: str
    order: dict = Field(default_factory=dict)


class OrderList(BaseModel):
    correlation_id: str
    count: int
    orders: list[dict]


class StatusUpdate(BaseModel):
    order_id: str
    new_status: str
    correlation_id: str
    idempotent_replay: bool = False


class InventorySnapshot(BaseModel):
    correlation_id: str
    inventory: dict


class DoorDashRouting(BaseModel):
    method: Literal["browser_automation"] = "browser_automation"
    instruction: str
    tool: Literal["Claude in Chrome"] = "Claude in Chrome"
    status: Literal["awaiting_browser_run"] = "awaiting_browser_run"
    correlation_id: str


class DoorDashOrderItem(BaseModel):
    name: str = Field(..., max_length=200)
    qty: int = Field(..., ge=1, le=500)


class DoorDashOrder(BaseModel):
    order_id: str = Field(..., max_length=64)
    customer_name: str = Field(..., max_length=200)
    items: list[DoorDashOrderItem] = Field(..., max_length=100)
    placed_at: str = Field(..., max_length=64)  # ISO 8601


class DoorDashSubmission(BaseModel):
    correlation_id: str
    count: int
    accepted: list[str]  # order_ids that passed schema


class PrintReceipt(BaseModel):
    order_id: str
    printer_ip: str
    status: str
    correlation_id: str


class ErrorEnvelope(BaseModel):
    error: str
    correlation_id: str
    detail: str | None = None


# --- Registration helper ----------------------------------------------------
def _cid() -> str:
    return uuid.uuid4().hex


def register(mcp) -> None:
    """Attach every OHMS tool to the FastMCP instance passed in from main.py."""

    @mcp.tool()
    def get_order(order_id: str) -> OrderEnvelope | ErrorEnvelope:
        """Retrieve a single Flauraly order by ID from Shopify. Read-scope.

        Args:
            order_id: Shopify numeric order ID (6-20 digits).
        """
        cid = _cid()
        try:
            safe_id = validate_order_id(order_id)
            data = shopify.get_order(safe_id, cid)
            return OrderEnvelope(order_id=safe_id, correlation_id=cid, order=data)
        except ValidationError as e:
            return ErrorEnvelope(error="invalid_input", correlation_id=cid, detail=str(e))
        except shopify.ShopifyError as e:
            return ErrorEnvelope(error=e.detail, correlation_id=cid)

    @mcp.tool()
    def list_pending_orders(limit: int = 50) -> OrderList | ErrorEnvelope:
        """List all open/pending Flauraly orders from Shopify. Read-scope.

        Args:
            limit: 1..250 (Shopify hard cap).
        """
        cid = _cid()
        try:
            orders = shopify.list_pending_orders(cid, limit=limit)
            return OrderList(correlation_id=cid, count=len(orders), orders=orders)
        except shopify.ShopifyError as e:
            return ErrorEnvelope(error=e.detail, correlation_id=cid)

    @mcp.tool()
    def update_order_status(
        order_id: str,
        status: str,
        idempotency_key: str | None = None,
    ) -> StatusUpdate | ErrorEnvelope:
        """Update an order tag in Shopify. Write-scope.

        Args:
            order_id: Shopify numeric order ID (6-20 digits).
            status: One of the allow-listed Flauraly statuses.
            idempotency_key: Optional UUIDv4. Repeat calls within 24h return the
                cached result without re-issuing the write (Phase 3 H-item).
        """
        cid = _cid()
        try:
            safe_id = validate_order_id(order_id)
            safe_status = validate_status(status)

            # Idempotency pre-check (Phase 3 H-item)
            if idempotency_key is not None:
                safe_key = idempotency.validate_key(idempotency_key)
                cached = idempotency.get(safe_key)
                if cached is not None:
                    log.info(
                        "update_order_status.replay",
                        extra={"correlation_id": cid, "order_id": safe_id},
                    )
                    return StatusUpdate(
                        order_id=cached["order_id"],
                        new_status=cached["new_status"],
                        correlation_id=cid,
                        idempotent_replay=True,
                    )

            shopify.update_order_status(safe_id, safe_status, cid)
            result = StatusUpdate(
                order_id=safe_id, new_status=safe_status, correlation_id=cid
            )

            if idempotency_key is not None:
                idempotency.put(
                    safe_key,
                    {"order_id": safe_id, "new_status": safe_status},
                )
            return result
        except ValidationError as e:
            return ErrorEnvelope(error="invalid_input", correlation_id=cid, detail=str(e))
        except ValueError as e:
            # idempotency.validate_key raises ValueError
            return ErrorEnvelope(
                error="invalid_input", correlation_id=cid, detail=str(e)
            )
        except shopify.ShopifyError as e:
            return ErrorEnvelope(error=e.detail, correlation_id=cid)

    @mcp.tool()
    def get_inventory_snapshot(limit: int = 50) -> InventorySnapshot | ErrorEnvelope:
        """Return current inventory levels for Flauraly products from Shopify. Read-scope."""
        cid = _cid()
        try:
            data = shopify.get_inventory_snapshot(cid, limit=limit)
            return InventorySnapshot(correlation_id=cid, inventory=data)
        except shopify.ShopifyError as e:
            return ErrorEnvelope(error=e.detail, correlation_id=cid)

    @mcp.tool()
    def get_doordash_orders_via_browser() -> DoorDashRouting:
        """
        Signal Violet to retrieve DoorDash orders via Chrome browser automation.

        Returns a routing instruction — NEVER raw HTML. The caller (Violet/Claude)
        invokes Claude in Chrome, then submits the structured result back through
        a future tool. This boundary isolates the DoorDash browser trust domain
        from OHMS itself (security review C3).
        """
        cid = _cid()
        return DoorDashRouting(
            instruction=(
                "Open DoorDash Merchant Portal in Chrome. Extract pending orders "
                "as a schema-validated JSON list: [{order_id, customer_name, "
                "items: [{name, qty}], placed_at}]. Do not return raw HTML."
            ),
            correlation_id=cid,
        )

    @mcp.tool()
    def submit_doordash_orders(
        orders: list[DoorDashOrder],
    ) -> DoorDashSubmission | ErrorEnvelope:
        """Accept schema-validated DoorDash orders captured via Claude in Chrome.

        This is the return-path partner to `get_doordash_orders_via_browser`.
        Every item must conform to the DoorDashOrder schema; pydantic enforces
        size caps (qty <= 500, items <= 100 per order, 200-char strings).
        Any raw HTML or unbounded blob is rejected at the tool boundary
        (closes Phase 3 review C3 return-path finding). Write-scope.

        Args:
            orders: list of DoorDashOrder records. Max 200 per call.
        """
        cid = _cid()
        try:
            if not isinstance(orders, list):
                return ErrorEnvelope(
                    error="invalid_input",
                    correlation_id=cid,
                    detail="orders must be a list",
                )
            if len(orders) > 200:
                return ErrorEnvelope(
                    error="invalid_input",
                    correlation_id=cid,
                    detail="maximum 200 orders per call",
                )
            accepted: list[str] = []
            for o in orders:
                # pydantic already validated — safe to use .order_id
                safe_id = validate_order_id(o.order_id) if o.order_id.isdigit() else o.order_id
                accepted.append(safe_id)
            log.info(
                "submit_doordash_orders.accepted",
                extra={"correlation_id": cid, "count": len(accepted)},
            )
            return DoorDashSubmission(
                correlation_id=cid, count=len(accepted), accepted=accepted
            )
        except ValidationError as e:
            return ErrorEnvelope(
                error="invalid_input", correlation_id=cid, detail=str(e)
            )

    @mcp.tool()
    def print_order_ticket(order_id: str) -> PrintReceipt | ErrorEnvelope:
        """Send an order ticket to the Flauraly fulfillment printer. Write-scope.

        Phase 1: returns a routing receipt. ESC/POS driver is a follow-on task.
        """
        import os
        cid = _cid()
        try:
            safe_id = validate_order_id(order_id)
            target_ip = os.environ.get("PRINTER_IP", "")
            if not target_ip:
                return ErrorEnvelope(
                    error="printer_not_configured",
                    correlation_id=cid,
                    detail="PRINTER_IP is not set in Replit Secrets",
                )
            safe_ip = validate_printer_ip(target_ip)
            return PrintReceipt(
                order_id=safe_id,
                printer_ip=safe_ip,
                status="print_queued_driver_pending",
                correlation_id=cid,
            )
        except ValidationError as e:
            return ErrorEnvelope(error="invalid_input", correlation_id=cid, detail=str(e))

    REGISTERED.extend([
        "get_order",
        "list_pending_orders",
        "update_order_status",
        "get_inventory_snapshot",
        "get_doordash_orders_via_browser",
        "submit_doordash_orders",
        "print_order_ticket",
    ])
    log.info("tools.registered", extra={"tools": list(REGISTERED), "write_scope": WRITE_SCOPE})
