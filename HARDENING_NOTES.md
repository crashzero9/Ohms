# HARDENING NOTES — OHMS Phase 1 → Phase 3

Closed + open security-review findings as of 2026-04-19.
Generated from the Phase 1, Phase 2, and Phase 3 security-review gates
(Violet workflow).

---

## CRITICAL — closed in code before deploy

| ID | Finding | Fix location |
|----|---------|--------------|
| C1 | Bearer token comparison was variable-time (`!=`) | `ohms/auth.py::_match_token` uses `hmac.compare_digest`; iterates every token so there is no short-circuit leak |
| C2 | Single shared token → no authz / no revocation / no audit | `ohms/auth.py` accepts `OHMS_API_TOKEN_READ` + `OHMS_API_TOKEN_WRITE`; legacy `OHMS_API_TOKEN` allowed but logs a loud `auth.legacy_single_token_mode` warning and is flagged as must-split-before-prod |
| C3 | DoorDash browser tool trust boundary | `ohms/tools.py::get_doordash_orders_via_browser` returns **only** a schema-constrained routing instruction. Never raw HTML. Caller (Violet) re-enters through a future typed tool after scraping. |
| C4 | `order_id` URL injection | `ohms/validators.py::validate_order_id` — regex `^\d{6,20}$` at every tool boundary; PUT bodies use `int(order_id)` so there's no string-concat risk |

## HIGH — closed in code before deploy

| ID | Finding | Fix location |
|----|---------|--------------|
| H1 | No rate limiting on public MCP endpoint | `ohms/rate_limit.py` — in-memory token bucket (60 req/min default) keyed on `(client_ip, token_prefix)`. Phase 1.5: upgrade to Redis-backed slowapi for multi-node. |
| H2 | `raise_for_status()` leaked upstream bodies | `ohms/shopify.py::_sanitize_and_raise` — logs full upstream body server-side only, raises `ShopifyError` with correlation id. Tools return `ErrorEnvelope{error, correlation_id}` — no upstream content exposed to MCP caller. |
| H3 | `httpx.Client` had no timeout | `ohms/shopify.py::_TIMEOUT` — explicit connect=3s, read=10s, write=5s, pool=2s |
| H4 | Secrets in logs | `ohms/logging_setup.py::JsonFormatter._scrub` redacts Authorization / X-Shopify-Access-Token / Cookie / Set-Cookie headers and known Shopify PII fields (email, phone, addresses, names). `uvicorn.access` logger disabled. |
| H5 | Shopify scope least-privilege | README.md documents required scopes: `read_orders`, `write_orders`, `read_inventory` ONLY. Token-issuance runbook lives in `docs/shopify_scope_runbook.md` (follow-on). |
| H6 | No TrustedHost / CORS policy | `main.py` wires `TrustedHostMiddleware(allowed_hosts=[OHMS_PUBLIC_HOST])` (skipped only if host is left as `*` during local dev) and `CORSMiddleware(allow_origins=[], allow_credentials=False)` (MCP clients aren't browsers; CORS is closed). |

## MEDIUM — closed in code

| ID | Finding | Fix location |
|----|---------|--------------|
| M1 | `/health` leakage risk | `ohms/health.py` returns strictly `{"ok": true}`. No version, no env info. |
| M2 | `PRINTER_IP` SSRF | `ohms/validators.py::validate_printer_ip` restricts to RFC1918 ranges (10/8, 172.16/12, 192.168/16); loopback and link-local are rejected. |
| M3 | No request-ID / structured logging | `ohms/correlation.py` assigns a 128-bit correlation id per request, echoes as `X-OHMS-Request-ID`. All logs are JSON with `correlation_id`. |
| M4 | Tool return types unvalidated | `ohms/tools.py` uses pydantic `BaseModel` return types (`OrderEnvelope`, `OrderList`, `StatusUpdate`, `InventorySnapshot`, `DoorDashRouting`, `PrintReceipt`, `ErrorEnvelope`). |

## MEDIUM — backlog

| ID | Finding | Status |
|----|---------|--------|
| M5 | No secret rotation runbook | `docs/secret_rotation_runbook.md` — full runbook in this repo; 60/90/180-day SLA documented. |

---

## PHASE 2 — closed at the handshake gate

| ID | Finding | Fix location |
|----|---------|--------------|
| P2-C1 | `/sse` could be mounted at root and bypass auth | `main.py` explicitly mounts `/mcp` and `/sse` as separate `Mount(...)` entries so the shared middleware stack wraps both transports. AttributeError fallback path preserved for combined-ASGI FastMCP builds. |
| P2-H1 | Verification script might log tokens | `scripts/verify_connection.py` reads `ANTHROPIC_API_KEY`, `OHMS_API_TOKEN_READ`, `OHMS_PUBLIC_URL` from env only and never prints payloads; does `/health` pre-check before sending any token. |
| P2-H2 | Docker Gateway config could be committed with a real token | `*-gateway.yaml` gitignored; only `*-gateway.example.yaml` (placeholder file) is committed. Runbook requires chmod 0600. |

## PHASE 3 — closed in code

| ID | Finding | Fix location |
|----|---------|--------------|
| P3-C1 | Shopify token scope drift undetected at runtime | `ohms/scope_check.py::assert_shopify_scopes` runs at startup in `main.py`. Requires **exactly** `{read_orders, write_orders, read_inventory}`; any extra or missing scope raises `ScopeViolation` and OHMS refuses to boot. |
| P3-C2 | DoorDash return-path tool could accept raw HTML blobs | `ohms/tools.py::submit_doordash_orders` takes a `list[DoorDashOrder]` with strict pydantic caps (`qty<=500`, `items<=100`, 200-char strings), max 200 orders per call. Anything else → `ErrorEnvelope(invalid_input)`. |
| P3-H1 | `update_order_status` had no idempotency — double-tap risk | `ohms/idempotency.py` 24h UUIDv4 cache; `tools.py::update_order_status` accepts optional `idempotency_key` param and returns `StatusUpdate(idempotent_replay=True)` on replay. UI Surface Contracts require the tablet + voice flows to generate a UUIDv4 per user action. |
| P3-M1 | No per-surface scope matrix | `docs/ui_surface_contracts.md` documents Order Board (read-only), User Tablet (write with idempotency), Voice Prompt (write with two-turn confirmation). |

## ACCEPTED RISKS — explicit

| ID | Finding | Owner |
|----|---------|-------|
| A1 | TLS termination at Replit edge (no e2e mTLS) | CTO, Phase 1 |
| A2 | Replit Reserved VM tenancy model | CTO |
| A3 | Single-region deployment, no HA | CTO, Phase 1 pilot |
| A4 | No WAF in front of Replit URL | CTO, pending traffic volume review |

---

## Hard blockers for promotion beyond pilot

1. **Per-tool token scoping** — currently enforced at transport edge (all non-`/health` requires a valid token). Phase 1.5 must split enforcement per-tool so write-scope is required for `update_order_status` and `print_order_ticket` at the FastMCP decorator layer.
2. **DoorDash browser isolation follow-up** — confirm Claude-in-Chrome instance runs under separate creds and cannot see Shopify tokens.
3. **Rate limiting backend** — in-memory → Redis before multi-node.
4. **Secrets rotation runbook complete and tested** (M5).

---

## Verification

- Run `pytest` — 54 tests pass:
  - `test_validators.py` (C4, M2)
  - `test_auth.py` (C1, C2)
  - `test_idempotency.py` (P3-H1)
  - `test_shopify_client.py` (H2, H3)
- Manual: `curl https://<host>/mcp` without Authorization → 401 `{"error":"unauthorized"}`.
- Manual: exceed `OHMS_RATE_LIMIT_PER_MIN` → 429 with `Retry-After` header.
- Manual: boot OHMS with a Shopify token that grants `write_customers` → startup
  exits with `OHMS refusing to start — Shopify token scope mismatch` (P3-C1).
- Manual: submit a DoorDash payload with `qty=10000` → `ErrorEnvelope(invalid_input)`.
