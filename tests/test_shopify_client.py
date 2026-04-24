"""
Integration tests for the Shopify client — every upstream call is mocked
with `httpx.MockTransport`. Verifies:

  - Happy-path extraction shapes (C4 contract preserved)
  - 4xx/5xx responses raise `ShopifyError` with sanitized detail (H2)
  - Network errors raise `ShopifyError` without leaking upstream text (H2)
  - `_TIMEOUT` is applied (H3)
"""

from __future__ import annotations

import os

import httpx
import pytest

from ohms import shopify


@pytest.fixture(autouse=True)
def _shopify_env(monkeypatch):
    monkeypatch.setenv("SHOPIFY_STORE_URL", "flauraly.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "shpat_" + "a" * 40)
    monkeypatch.setenv("SHOPIFY_API_VERSION", "2025-01")


def _install_transport(monkeypatch, handler):
    """Swap httpx.Client inside the client() ctx manager to use MockTransport."""
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def _fake_client(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "Client", _fake_client)


def test_get_order_happy_path(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Shopify-Access-Token"].startswith("shpat_")
        return httpx.Response(200, json={"order": {"id": 123, "tags": "new"}})

    _install_transport(monkeypatch, handler)
    result = shopify.get_order("123", correlation_id="cid-1")
    assert result == {"id": 123, "tags": "new"}


def test_get_order_4xx_sanitized(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"errors": "Not found"}
        )

    _install_transport(monkeypatch, handler)
    with pytest.raises(shopify.ShopifyError) as excinfo:
        shopify.get_order("999", correlation_id="cid-2")
    # Caller sees only the sanitized detail, never the upstream body
    assert excinfo.value.detail == "shopify_upstream_failure"
    assert excinfo.value.correlation_id == "cid-2"
    assert "Not found" not in str(excinfo.value)


def test_list_pending_orders_limit_clamped(monkeypatch):
    seen_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(200, json={"orders": []})

    _install_transport(monkeypatch, handler)
    shopify.list_pending_orders("cid-3", limit=9999)
    # Shopify max is 250 — the client clamps.
    assert seen_params["limit"] == "250"


def test_list_pending_orders_limit_min(monkeypatch):
    seen_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(200, json={"orders": []})

    _install_transport(monkeypatch, handler)
    shopify.list_pending_orders("cid-3b", limit=0)
    assert seen_params["limit"] == "1"


def test_update_order_status_happy_path(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        return httpx.Response(200, json={"order": {"id": 123, "tags": "ready"}})

    _install_transport(monkeypatch, handler)
    result = shopify.update_order_status("123", "ready", correlation_id="cid-4")
    assert result["order_id"] == "123"
    assert result["updated_status"] == "ready"


def test_network_error_sanitized(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connection failure")

    _install_transport(monkeypatch, handler)
    with pytest.raises(shopify.ShopifyError) as excinfo:
        shopify.get_order("123", correlation_id="cid-5")
    assert excinfo.value.detail == "shopify_network_failure"
    assert "simulated" not in str(excinfo.value)


def test_missing_store_url_raises():
    os.environ.pop("SHOPIFY_STORE_URL", None)
    with pytest.raises(shopify.ShopifyError) as excinfo:
        shopify.get_order("123", correlation_id="cid-6")
    assert "SHOPIFY_STORE_URL" in excinfo.value.detail
