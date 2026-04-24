# OHMS — Replit Deployment Runbook

End-to-end deployment and verification. Follow these steps in order. Every
step has a pass signal; do not advance on a fail.

All commands assume the Replit shell (bash). Placeholder values are shown as
`<ALL_CAPS>` and must be filled from the corresponding entry in
`README.md → Replit Secrets to configure`.

---

## Phase 1 — Scaffold live on a Replit Repl

**Goal:** OHMS runs on a free Repl, `/health` returns `{"ok": true}`, and the
tool list answers at `/mcp`.

1. Create a new Python Repl from this repo. Replit will auto-detect
   `pyproject.toml` and `.replit`.
2. In **Secrets**, set:
   - `OHMS_API_TOKEN_READ` = `openssl rand -hex 32`
   - `OHMS_API_TOKEN_WRITE` = `openssl rand -hex 32` (different)
   - `PORT` = `8080`
3. Click **Run**. Expected log lines:
   ```
   ohms.logging_setup: configured
   ohms.auth: bearer_auth_ready (tokens_configured=2)
   ohms.tools: tools.registered tools=[...]
   ohms.main: OHMS starting ... tool_count=7
   ```
4. In the Repl shell:
   ```bash
   curl -sS http://localhost:8080/health
   ```
   → `{"ok": true}`
5. Tool list (inside the Repl, so no host check):
   ```bash
   TOKEN="$OHMS_API_TOKEN_READ"
   curl -sS -X POST http://localhost:8080/mcp \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
   ```
   Expect 7 tools in the JSON response.

**Fail signals**
- `tool_count=0` → `ohms/tools.py` not imported by `main.py`; check import path.
- `401` on `/mcp` → token not set in Secrets or not sourced into the shell.

---

## Phase 2 — Promote to Reserved VM, verify handshake

**Goal:** always-on deployment, `TrustedHost` locked to the assigned host,
and the Claude MCP Connector handshake succeeds end-to-end.

1. **Deploy → Reserved VM → Smallest tier → Web server.**
2. After deploy, Replit assigns a hostname like
   `ohms.<username>.replit.app`.
3. Add two more Secrets:
   - `OHMS_PUBLIC_HOST` = the assigned hostname (no scheme, no slash)
   - `OHMS_LOG_LEVEL` = `INFO`
4. Redeploy to pick up `OHMS_PUBLIC_HOST`.
5. From your local laptop:
   ```bash
   curl -sS https://<OHMS_PUBLIC_HOST>/health
   ```
   → `{"ok": true}`
6. Run the connection verifier:
   ```bash
   export ANTHROPIC_API_KEY=...              # NOT committed, not logged
   export OHMS_API_TOKEN_READ=...            # the value from Replit Secrets
   export OHMS_PUBLIC_URL=https://<OHMS_PUBLIC_HOST>
   python scripts/verify_connection.py
   ```
   → `[verify] PASS — Phase 2 handshake confirmed`
7. Walk the full 4-point sign-off at `docs/phase2_checklist.md`. File
   evidence into `docs/phase2_evidence/` (gitignored).

**Fail signals**
- `403` on `/mcp` from outside the Repl → `OHMS_PUBLIC_HOST` missing or wrong.
- Verifier sees 0 tools → FastMCP mount path broken; the Phase 1 shell test
  already caught this if it passes inside the Repl.

---

## Phase 3 — Wire real Shopify data

**Goal:** live orders from Shopify via the 5 Shopify-backed tools. OHMS
refuses to boot if the token's scopes don't match exactly.

1. In Shopify admin, create a custom app with **exactly** these scopes:
   - `read_orders`
   - `write_orders`
   - `read_inventory`
2. Install in the Flauraly store; copy the admin API access token.
3. In Replit → Secrets:
   - `SHOPIFY_STORE_URL` = `flauraly.myshopify.com`
   - `SHOPIFY_ACCESS_TOKEN` = <token from step 2, never paste in chat>
   - `SHOPIFY_API_VERSION` = `2025-01`
4. Redeploy. Watch for:
   ```
   ohms.scope_check: scope_check.ok granted=[read_inventory,read_orders,write_orders]
   ohms.main: OHMS starting ... tool_count=7
   ```
5. If you see `scope_check.mismatch` followed by `OHMS refusing to start —
   Shopify token scope mismatch`, **do not** widen scopes to make it boot.
   Recreate the app in Shopify with exactly the three scopes.
6. Live test from Violet / Claude:
   ```
   list_pending_orders(limit=5)
   ```
   → expect `OrderList` with real order dicts. No raw Shopify bodies — only
   the shape documented in `tools.py`.

**Fail signals**
- `ScopeViolation: shopify scope mismatch` → fix in Shopify, not in code.
- `ShopifyError.detail == "shopify_upstream_failure"` with a correlation_id
  → grep logs for that correlation_id; the detail is server-side only.

---

## Phase 3 (cont.) — DoorDash browser round-trip

1. On the operator laptop, make sure Claude in Chrome is installed and the
   DoorDash Merchant Portal session is fresh.
2. Violet calls `get_doordash_orders_via_browser()`.
3. The operator runs the shortcut that drives Claude in Chrome to extract
   orders into the schema described in
   `docs/doordash_browser_contract.md`.
4. Violet (or the operator) calls `submit_doordash_orders(orders=[...])`.
5. Expected result: `DoorDashSubmission` with `count` matching the extracted
   list length and `accepted` listing the validated order IDs.

**Fail signals**
- `ErrorEnvelope(error=invalid_input)` → schema violation; inspect the
  rejected record against the rules in
  `docs/doordash_browser_contract.md`.
- Raw HTML showing up in a tool arg → stop immediately; the browser shortcut
  is mis-configured. OHMS will reject it but the operator workflow needs a fix.

---

## Phase 3 (cont.) — Printer wiring

1. In Replit → Secrets, set `PRINTER_IP` to the printer's RFC1918 address
   (e.g., `192.168.1.42`).
2. Redeploy.
3. Tablet calls `print_order_ticket(order_id=<real order>)`.
4. Expected: `PrintReceipt` with `status=print_queued_driver_pending`. The
   ESC/POS driver is a follow-on task; the scaffold returns the routing
   receipt in Phase 3.

**Fail signals**
- `invalid_input: printer_ip must be RFC1918 private` → you configured a
  public IP; correct to a LAN address.
- `printer_not_configured` → `PRINTER_IP` Secret is empty.

---

## Sign-off

- [ ] Phase 1 complete — `tool_count=7`, `/health` green
- [ ] Phase 2 complete — 4-point checklist all green, evidence filed
- [ ] Phase 3 Shopify — `scope_check.ok` in logs, `list_pending_orders`
      returns live data
- [ ] Phase 3 DoorDash — round-trip demonstrates `submit_doordash_orders`
      accepts schema, rejects blobs
- [ ] Phase 3 Printer — `print_order_ticket` returns `PrintReceipt`

On full green, file a Dispatch to CTO. Ongoing operations run under
`docs/secret_rotation_runbook.md`.
