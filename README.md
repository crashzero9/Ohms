# OHMS — Flauraly Order Hub Management System

**Phase 1 scaffold — Python FastMCP on Replit Reserved VM.**

This is the Phase-1 build of OHMS, the MCP server that ingests orders from
Shopify and DoorDash, manages inventory state, and surfaces data to the
Order Board, User Tablet, and Voice Prompt UIs. Deployed to a Replit
Reserved VM and consumed by Violet/Claude via the Claude MCP Connector API.

All security-review findings from the Phase 1 gate (2026-04-19) are
addressed in code. See `HARDENING_NOTES.md` for the full closed-finding
register.

---

## Layout

```
ohms/
├── main.py                  — app entry, middleware stack, ASGI assembly
├── ohms/
│   ├── __init__.py
│   ├── auth.py              — Bearer auth w/ hmac.compare_digest + scopes
│   ├── correlation.py       — X-OHMS-Request-ID middleware
│   ├── health.py            — /health minimal JSON
│   ├── logging_setup.py     — structured JSON logs w/ secret/PII scrubbing
│   ├── rate_limit.py        — in-memory token bucket, 60 req/min default
│   ├── shopify.py           — hardened Shopify REST client
│   ├── scope_check.py       — Shopify scope assertion at startup (Phase 3)
│   ├── idempotency.py       — 24h UUIDv4 cache for write tools (Phase 3)
│   ├── tools.py             — all 7 FastMCP @tool definitions
│   └── validators.py        — order_id, status, printer_ip validators
├── tests/
│   ├── test_auth.py
│   └── test_validators.py
├── requirements.txt
├── pyproject.toml
├── .replit                  — Reserved VM deploy target
├── replit.nix
├── Dockerfile               — optional container deploy
├── .env.example             — env schema (NO SECRETS)
├── .gitignore
├── README.md                — you are here
└── HARDENING_NOTES.md       — closed security findings + open backlog
```

---

## Required Shopify API scopes (H5)

The access token must have **exactly** these scopes — nothing more:

- `read_orders`
- `write_orders`
- `read_inventory`

Reject any token that has `write_products`, `write_customers`, or
`read_all_orders` — those widen the blast radius.

---

## Replit Secrets to configure

| Key | Value | Required for |
|---|---|---|
| `OHMS_API_TOKEN_READ` | `openssl rand -hex 32` | Phase 1 |
| `OHMS_API_TOKEN_WRITE` | `openssl rand -hex 32` (different value) | Phase 1 |
| `OHMS_PUBLIC_HOST` | e.g. `ohms.<username>.replit.app` | Phase 1 (post-deploy) |
| `PORT` | `8080` | Phase 1 |
| `SHOPIFY_STORE_URL` | e.g. `flauraly.myshopify.com` | Phase 3 |
| `SHOPIFY_ACCESS_TOKEN` | From Obsidian vault | Phase 3 |
| `SHOPIFY_API_VERSION` | `2025-01` | Phase 3 |
| `PRINTER_IP` | RFC1918 private IP only | Phase 3 |
| `OHMS_LOG_LEVEL` | `INFO` (default) | optional |
| `OHMS_RATE_LIMIT_PER_MIN` | `60` | optional |

Legacy single-token mode: set `OHMS_API_TOKEN` only if the scoped pair is
not in use. The server will log a warning on startup and treat the single
token as both read and write.

---

## MCP tool registry

| Tool | Scope | Returns |
|---|---|---|
| `get_order(order_id)` | read | `OrderEnvelope` |
| `list_pending_orders(limit)` | read | `OrderList` |
| `update_order_status(order_id, status, idempotency_key?)` | write | `StatusUpdate` |
| `get_inventory_snapshot(limit)` | read | `InventorySnapshot` |
| `get_doordash_orders_via_browser()` | read | `DoorDashRouting` (never raw HTML) |
| `submit_doordash_orders(orders)` | write | `DoorDashSubmission` (schema-validated return path) |
| `print_order_ticket(order_id)` | write | `PrintReceipt` |

All tools return `ErrorEnvelope` on validation or upstream failure. No
upstream Shopify body is ever returned to the caller — only an `error` tag
and the server's `correlation_id` for audit lookup.

---

## Running locally (Replit)

1. Click **Run**. Replit auto-installs from `requirements.txt`.
2. Server binds to `0.0.0.0:8080`.
3. `curl http://localhost:8080/health` → `{"ok": true}`
4. `curl -H "Authorization: Bearer $OHMS_API_TOKEN_READ" http://localhost:8080/mcp -X POST -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' -H "Content-Type: application/json"` → returns tool list

## Deploying (Replit Reserved VM)

1. **Deploy → Reserved VM → Smallest tier → Web server**
2. After deploy, set `OHMS_PUBLIC_HOST` to the assigned hostname
   (e.g., `ohms.laura-flauraly.replit.app`), then redeploy to activate
   `TrustedHostMiddleware`.
3. Confirm public URL: `curl https://<host>/health` → `{"ok": true}`

## Running tests

```bash
pip install -e '.[test]'
pytest
```

---

## Phase 2 / Phase 3

- **Phase 2 verification**: see `docs/phase2_checklist.md` and
  `scripts/verify_connection.py` in the project root.
- **Phase 3 UI surface contracts**: see `docs/ui_surface_contracts.md`.
- **Docker MCP Gateway config**: see `docker-gateway/`.

---

## Source of truth

- Canonical brief: `../VIOLET-BRIEF-OHMS-Build.md`
- CTO master copy: `C:\Users\laura\OneDrive\Documents\Flauraly\AI\Projects\Claude\VIOLET-BRIEF-OHMS-Build.md`
