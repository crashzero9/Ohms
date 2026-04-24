# Secret Rotation Runbook

All OHMS secrets live in Replit Secrets. This runbook describes how to rotate
each one safely, with no downtime for the active Order Board / Tablet / Voice
surfaces.

**Golden rule:** never paste a secret into a chat prompt, a commit message,
or a doc. Generate and paste directly into the Replit Secrets UI.

---

## Cadence

| Secret | Routine cadence | Triggered rotation |
|---|---|---|
| `OHMS_API_TOKEN_READ` | every 90 days | suspected leak, device loss |
| `OHMS_API_TOKEN_WRITE` | every 60 days | suspected leak, device loss, staff change |
| `SHOPIFY_ACCESS_TOKEN` | every 180 days | suspected leak, scope drift |
| `PRINTER_IP` | on LAN re-configuration | printer replacement |
| Docker Gateway laptop-token | every 90 days | laptop reassignment |

---

## 1 — Rotate `OHMS_API_TOKEN_READ`

Used by: Order Board only.

1. Generate a new token locally:
   ```bash
   openssl rand -hex 32
   ```
2. In Replit → Secrets, **add** `OHMS_API_TOKEN_READ_NEXT` with the new value.
3. Redeploy OHMS. The auth module accepts any configured token.
4. Update the Order Board device to use the new token.
5. Confirm traffic: watch logs for `auth.ok` with the new token's prefix.
6. Remove `OHMS_API_TOKEN_READ` (the old one). Rename `*_NEXT` to `OHMS_API_TOKEN_READ`.
7. Redeploy.

---

## 2 — Rotate `OHMS_API_TOKEN_WRITE`

Used by: User Tablet + Voice Prompt.

Same dual-key pattern as above, but test each surface before retiring the old
token:

1. Generate new token with `openssl rand -hex 32`.
2. Set `OHMS_API_TOKEN_WRITE_NEXT` in Replit Secrets.
3. Redeploy.
4. Update the tablet. Run one test write with an idempotency_key. Confirm a
   `StatusUpdate` result in logs.
5. Update the voice surface. Run one test voice command end-to-end.
6. Remove the old `OHMS_API_TOKEN_WRITE`, rename `*_NEXT`.
7. Redeploy.

---

## 3 — Rotate `SHOPIFY_ACCESS_TOKEN`

This is the highest-blast-radius token. Rotate with care.

1. In the Shopify admin, create a **new** custom app with exactly these scopes
   — nothing more:
   - `read_orders`
   - `write_orders`
   - `read_inventory`
2. Install the app in the Flauraly store and copy the access token.
3. In Replit → Secrets, set `SHOPIFY_ACCESS_TOKEN` to the new value.
4. Redeploy. The `scope_check` at startup will **refuse to boot** if the token
   grants extra scopes (`write_customers`, `read_all_orders`, etc.). This is
   a feature — fix the scopes in Shopify before retrying.
5. Watch for `scope_check.ok` in logs with the granted set.
6. Uninstall the old Shopify app to revoke its token.

If step 4 fails with `ScopeViolation`, **do not** override it. Recreate the
app with the exact scope set.

---

## 4 — Rotate `PRINTER_IP`

Used by: `print_order_ticket`. Must be an RFC1918 private address.

1. In Replit → Secrets, update `PRINTER_IP` to the new address.
2. The `validate_printer_ip` validator allows only:
   - `10.0.0.0/8`
   - `172.16.0.0/12`
   - `192.168.0.0/16`
3. A public IP will be rejected with `ErrorEnvelope(error=invalid_input)`.
4. Restart OHMS. Run a test print from the tablet.

---

## 5 — Rotate Docker Gateway laptop-token

Used by: the operator's laptop (Claude Desktop) to reach OHMS.

The gateway config file is gitignored. The token itself is one of the OHMS
read/write tokens (whichever scope the laptop needs).

1. Rotate the underlying `OHMS_API_TOKEN_READ` or `OHMS_API_TOKEN_WRITE`
   following sections 1 or 2 above.
2. On the laptop, edit `docker-gateway/ohms-gateway.yaml` (mode 0600) and
   replace the bearer value.
3. Restart the Docker MCP gateway:
   ```bash
   docker mcp gateway run --log-level=info
   ```
4. Confirm in Claude Desktop that the OHMS tools still resolve.

---

## 6 — Incident rotation (suspected leak)

If any token is suspected leaked:

1. **Immediately** set a new value in Replit Secrets (no dual-key wait).
2. Redeploy OHMS.
3. Update the downstream surface that owns the token.
4. File a Dispatch to CTO with:
   - Which token
   - When leak was suspected
   - What device / user the old token lived on
5. Review logs for any requests made with the old token prefix after the
   suspected leak window.

Never log the token value itself during investigation. The logging filter
already scrubs it — do not defeat the filter.

---

## Never-do list

- Never commit a populated `*-gateway.yaml` (gitignored for a reason).
- Never paste a token into a chat prompt to any LLM, including Claude.
- Never put a token in a commit message, even partially.
- Never reuse a retired token. If rotated, it is gone forever.
- Never grant extra Shopify scopes "just in case" — OHMS refuses to boot
  against a scope-mismatched token.
