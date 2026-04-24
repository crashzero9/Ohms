# OHMS — Deliverable Index

Full Phase 1 → Phase 3 build. 54 tests pass. All C/H security-review findings
closed; M5 (secret rotation) is now fully documented.

---

## 1 — Replit-ready project scaffold

| File | Purpose |
|---|---|
| [main.py](main.py) | App entry, middleware stack, ASGI assembly, Shopify scope assertion at boot |
| [pyproject.toml](pyproject.toml) | Python deps, test config |
| [requirements.txt](requirements.txt) | Install manifest (Replit auto-picks up) |
| [.replit](.replit) | Replit run target |
| [replit.nix](replit.nix) | Replit Nix toolchain |
| [Dockerfile](Dockerfile) | Optional container deploy |
| [.env.example](.env.example) | Env schema — no secrets |
| [.gitignore](.gitignore) | Blocks .env, populated gateway configs, secret-scan artifacts |

### Module layout — `ohms/`
| File | Purpose |
|---|---|
| [ohms/auth.py](ohms/auth.py) | Bearer auth with `hmac.compare_digest`, scoped READ/WRITE tokens |
| [ohms/correlation.py](ohms/correlation.py) | `X-OHMS-Request-ID` middleware, 128-bit per-request IDs |
| [ohms/health.py](ohms/health.py) | `/health` returns strict `{"ok": true}` |
| [ohms/logging_setup.py](ohms/logging_setup.py) | JSON logs, secret/PII scrubbing filter |
| [ohms/rate_limit.py](ohms/rate_limit.py) | In-memory token bucket, 60 req/min default |
| [ohms/shopify.py](ohms/shopify.py) | Hardened Shopify REST client, sanitized upstream errors |
| [ohms/scope_check.py](ohms/scope_check.py) | Boot-time Shopify scope assertion (Phase 3 C1) |
| [ohms/idempotency.py](ohms/idempotency.py) | 24h UUIDv4 cache for write tools (Phase 3 H1) |
| [ohms/tools.py](ohms/tools.py) | All 7 FastMCP `@tool` definitions with pydantic return types |
| [ohms/validators.py](ohms/validators.py) | `order_id`, `status`, `printer_ip` validators |

### Tests — `tests/`
| File | Coverage |
|---|---|
| [tests/test_auth.py](tests/test_auth.py) | Scoped token loading, Bearer matching, constant-time compare |
| [tests/test_validators.py](tests/test_validators.py) | order_id / status / printer_ip (C4, M2) |
| [tests/test_idempotency.py](tests/test_idempotency.py) | UUIDv4 validation, cache hit/miss, collision avoidance |
| [tests/test_shopify_client.py](tests/test_shopify_client.py) | Mocked Shopify happy-path + sanitized 4xx/5xx + network failure |

---

## 2 — Step-by-step Replit runbook

| File | Purpose |
|---|---|
| [docs/replit_runbook.md](docs/replit_runbook.md) | Full Phase 1 → Phase 3 deployment runbook with pass/fail signals per step |
| [docs/phase2_checklist.md](docs/phase2_checklist.md) | 4-point sign-off checklist with evidence format |
| [scripts/verify_connection.py](scripts/verify_connection.py) | Phase 2 handshake verifier — env-only, never logs payloads |

---

## 3 — Shopify + DoorDash ingestion stubs

- Shopify client implemented: `ohms/shopify.py` (4 endpoints wired: get_order, list_pending_orders, update_order_status, get_inventory_snapshot). Integration tests mock all upstream paths.
- DoorDash round-trip defined by contract rather than code, because DoorDash has no first-party ingest API. The two tools that complete the boundary:
  - `get_doordash_orders_via_browser()` → returns `DoorDashRouting` instruction (no raw HTML)
  - `submit_doordash_orders(orders)` → accepts schema-validated `list[DoorDashOrder]`, rejects anything else.

| File | Purpose |
|---|---|
| [docs/doordash_browser_contract.md](docs/doordash_browser_contract.md) | Full round-trip spec, schema rules, mock payload |

---

## 4 — UI surface contracts

| File | Purpose |
|---|---|
| [docs/ui_surface_contracts.md](docs/ui_surface_contracts.md) | Order Board / User Tablet / Voice Prompt tool allowlists, scope tokens, voice two-turn confirmation rule |

---

## 5 — Docker MCP Gateway wiring (laptop-side)

| File | Purpose |
|---|---|
| [docker-gateway/ohms-gateway.example.yaml](docker-gateway/ohms-gateway.example.yaml) | Placeholder template — no secrets. Populated copy is gitignored. |
| [docker-gateway/README.md](docker-gateway/README.md) | Laptop-side setup instructions |

---

## 6 — Operations

| File | Purpose |
|---|---|
| [docs/secret_rotation_runbook.md](docs/secret_rotation_runbook.md) | Per-secret rotation procedure, cadence, incident rotation |
| [HARDENING_NOTES.md](HARDENING_NOTES.md) | Closed + open security-review findings, Phase 1/2/3 |

---

## Security posture at a glance

- **54 / 54 tests pass.**
- **All CRITICAL findings closed** (C1–C4, P2-C1, P3-C1, P3-C2).
- **All HIGH findings closed** (H1–H6, P2-H1/H2, P3-H1).
- **No secrets in any committed file.** `.gitignore` blocks `.env*` (except `.env.example`), populated `*-gateway.yaml`, and gitleaks artifacts.
- **Shopify scope fail-closed at boot.** A mis-minted token refuses to start the server.
- **DoorDash return path is schema-only.** Raw HTML cannot cross the boundary.
- **Every write tool supports idempotency keys.** Two-turn confirmation required for voice writes.

---

## Operator checklist before Phase 3 go-live

- [ ] Replit Reserved VM provisioned; `OHMS_PUBLIC_HOST` Secret set.
- [ ] `OHMS_API_TOKEN_READ` + `OHMS_API_TOKEN_WRITE` rolled with `openssl rand -hex 32`.
- [ ] Shopify custom app created with **exactly** `read_orders, write_orders, read_inventory`.
- [ ] `SHOPIFY_ACCESS_TOKEN`, `SHOPIFY_STORE_URL`, `SHOPIFY_API_VERSION` set in Replit Secrets.
- [ ] `PRINTER_IP` set to the in-shop printer's RFC1918 address.
- [ ] Verified boot log shows `scope_check.ok` and `tool_count=7`.
- [ ] Phase 2 4-point checklist green, evidence filed in `docs/phase2_evidence/` (gitignored).
- [ ] DoorDash round-trip exercised once against the mock payload.
- [ ] Tablet + Voice surface tokens provisioned per `docs/ui_surface_contracts.md`.
