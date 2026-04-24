# Phase 2 — Sign-Off Checklist

Run this after the Reserved VM is live (Phase 1 Step 7). All four must pass
before Phase 3 wires real Shopify/DoorDash data.

Evidence format: for each check, capture either (a) the exact CLI output
(with token values elided as `[REDACTED]`) or (b) a screenshot. File evidence
into `docs/phase2_evidence/` — that folder is gitignored.

---

## [ ] Check 1 — `/health` returns `{"ok": true}`

```bash
curl -sS https://ohms.<USERNAME>.replit.app/health
```

**Expected:** `{"ok": true}` and HTTP 200.
**Why it matters:** proves DNS, TLS, Reserved VM, and middleware wiring are all alive.
**If it fails:** stop and dispatch. Likely causes: VM not deployed, port mismatch, bad TrustedHost config.

---

## [ ] Check 2 — Claude API discovers all 7 OHMS tools

```bash
export ANTHROPIC_API_KEY=...
export OHMS_API_TOKEN_READ=...
export OHMS_PUBLIC_URL=https://ohms.<USERNAME>.replit.app
python scripts/verify_connection.py
```

**Expected:**
```
[verify] env check: OK (no values logged)
[verify] anthropic SDK version: 0.40.x
[verify] MCP Connector beta header: mcp-client-2025-11-20
[verify] /health: OK
[verify] tool-listing handshake: OK (7 tools discovered)
[verify] PASS — Phase 2 handshake confirmed
```

**Why it matters:** proves Violet/Claude can actually see OHMS via the beta connector.
**If it fails:**
- 401 → token not set on Replit or scope mismatch
- 429 → rate limit; wait 60s and retry
- 0 tools → FastMCP app not mounted under `/mcp`; check main.py

---

## [ ] Check 3 — Docker MCP Gateway connects to `/sse` without errors

```bash
cd docker-gateway
cp ohms-gateway.example.yaml ohms-gateway.yaml
$EDITOR ohms-gateway.yaml   # populate URL and LAPTOP-specific token
chmod 0600 ohms-gateway.yaml
docker mcp profile server add flauraly --server file://$(pwd)/ohms-gateway.yaml
docker mcp gateway run --log-level=info
```

**Expected:** gateway starts clean, no 401/403, no stack traces.
**Log hygiene verification:** the output MUST NOT contain any `Authorization:` header value.

**Why it matters:** proves the laptop-side transport works with OHMS auth.
**If it fails:** check YAML permissions (must be 0600), verify the laptop-specific token is registered in Replit Secrets, check the URL has `/sse` not `/mcp`.

---

## [ ] Check 4 — Claude Desktop sees OHMS tools

1. Restart Claude Desktop after the gateway is running.
2. In a new conversation, ask: *"What tools do you have available?"*
3. All 6 OHMS tool names should appear:
   - `get_order`
   - `list_pending_orders`
   - `update_order_status`
   - `get_inventory_snapshot`
   - `get_doordash_orders_via_browser`
   - `print_order_ticket`

**Evidence:** screenshot of the tool list.
**If it fails:** verify the gateway is still running; check `docker mcp gateway status`; reconnect server profile.

---

## Gate decision

- [ ] All four checks pass → **GO** to Phase 3 (wire real data).
- [ ] Any check fails → **STOP** and send a Dispatch report to CTO.

_Do not proceed to Phase 3 until all four are checked._
