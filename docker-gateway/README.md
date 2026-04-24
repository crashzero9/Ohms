# Docker MCP Gateway — OHMS entry

This directory contains the Docker MCP Gateway config that lets
**Claude Desktop** (on Alroy's laptop) talk to the Replit-hosted OHMS server.

The Claude API connects to OHMS directly via `/mcp` (Streamable HTTP). The
Docker Gateway is only for Claude Desktop — it proxies the `/sse` transport.

## Files

- `ohms-gateway.example.yaml` — committed template (no secrets)
- `ohms-gateway.yaml` — **NEVER commit**, gitignored via `*-gateway.yaml`

## Setup (operator laptop, one time)

1. Generate a **laptop-specific** OHMS write-scope token. Do NOT reuse the
   verification-script token or any long-lived token:

   ```bash
   openssl rand -hex 32
   ```

2. Add it as an **additional** Replit Secret, e.g. `OHMS_API_TOKEN_WRITE_LAPTOP`.
   Register it with OHMS's auth module (future: add token-registry table so
   multiple scoped tokens can coexist and be revoked independently). For
   Phase 2 today, rotate the primary `OHMS_API_TOKEN_WRITE` value and
   distribute the new one only to this laptop.

3. Copy the template and populate:

   ```bash
   cp ohms-gateway.example.yaml ohms-gateway.yaml
   $EDITOR ohms-gateway.yaml          # replace URL + token
   chmod 0600 ohms-gateway.yaml
   ```

4. Register with Docker MCP Gateway:

   ```bash
   docker mcp profile server add flauraly --server file://$(pwd)/ohms-gateway.yaml
   docker mcp gateway run
   ```

5. Restart Claude Desktop. In Claude Desktop, ask:
   *"What tools do you have available?"* — all 6 OHMS tools should appear.

## Log-hygiene check (Phase 2 security review H-item)

Before trusting the gateway with a write-scope token, confirm Docker MCP
Gateway does not log the `Authorization` header:

```bash
docker mcp gateway run --log-level=info 2>&1 | grep -i authorization
# expected: no output
```

If any output appears, **stop** and report via Dispatch before issuing a
write-scope token. OHMS's own JSON-log scrubbing does not protect the laptop.

## Rotation SLA

- Laptop-specific gateway token: 30-day TTL.
- Phase 2 MVP enforces rotation manually. Phase 1.5 backlog: token-registry
  with automatic TTL in `ohms/auth.py`.

## If the laptop is lost

1. In Replit → Secrets, invalidate the laptop token (rotate to fresh value).
2. Restart the Replit deployment to pick up the new secret.
3. On a new laptop, repeat the setup from step 1 with a fresh token.
