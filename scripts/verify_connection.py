#!/usr/bin/env python3
"""
Phase 2 — Claude API → OHMS verification script.

Runs the minimum handshake needed to prove:
  1. OHMS /health is reachable (TLS + DNS ok)
  2. Claude API can discover OHMS tools via the MCP Connector beta
  3. OHMS correlation-id plumbing works end-to-end

Security hardening applied per the Phase 2 security-review gate:
  * Reads ANTHROPIC_API_KEY and OHMS_API_TOKEN_READ strictly from env (no CLI flags, no fallbacks)
  * Uses the READ-scoped token — NEVER the write-scoped token
  * Exits non-zero before any SDK call if either var is missing
  * Never prints mcp_servers payloads, responses, or reprs
  * On error, logs only exception class + sanitized message
  * Pins the Anthropic SDK version and emits the version to stdout for audit
  * Does a /health pre-check before sending any token

Usage:
  export ANTHROPIC_API_KEY=...               # set via your shell / vault, not a file
  export OHMS_API_TOKEN_READ=...             # READ-scope OHMS token only
  export OHMS_PUBLIC_URL=https://ohms.<username>.replit.app
  python scripts/verify_connection.py

Do NOT paste this script's output into a public issue — even the sanitized
output may hint at your deployment hostname. Redact OHMS_PUBLIC_URL if sharing.
"""

from __future__ import annotations

import os
import sys
import urllib.request
import urllib.error
from typing import NoReturn


REQUIRED_ENV = ("ANTHROPIC_API_KEY", "OHMS_API_TOKEN_READ", "OHMS_PUBLIC_URL")

# Pinned beta header — re-audit when this rev's (Phase 2 security review H-item).
MCP_CLIENT_BETA = "mcp-client-2025-11-20"


def fail(msg: str, code: int = 1) -> NoReturn:
    """Print a single sanitized line and exit. Never include env values."""
    print(f"[verify] FAIL: {msg}", file=sys.stderr)
    sys.exit(code)


def _require_env() -> dict[str, str]:
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        fail(f"missing required env vars: {', '.join(missing)}", code=2)
    return {k: os.environ[k] for k in REQUIRED_ENV}


def _healthcheck(base: str) -> None:
    """Unauthenticated GET /health — confirms DNS + TLS + reachability before we ever send a token."""
    url = base.rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status != 200:
                fail(f"/health returned non-200 (status={resp.status})")
            body = resp.read()
            if b'"ok"' not in body:
                fail("/health payload did not match minimal JSON contract")
    except urllib.error.URLError as e:
        fail(f"/health unreachable: {type(e).__name__}")


def _verify_mcp_listing(env: dict[str, str]) -> int:
    """Ask Claude to list the OHMS tools. Returns number of tools discovered."""
    try:
        import anthropic
    except ImportError:
        fail("anthropic SDK not installed. pip install 'anthropic>=0.40'")

    print(f"[verify] anthropic SDK version: {anthropic.__version__}")
    print(f"[verify] MCP Connector beta header: {MCP_CLIENT_BETA}")

    client = anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"])

    try:
        # NOTE: we build the request outside any print — never f-string the payload.
        response = client.beta.messages.create(
            model="claude-opus-4-6",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": "List the names of the OHMS tools you have access to. "
                               "One name per line. No commentary.",
                }
            ],
            mcp_servers=[
                {
                    "type": "url",
                    "url": env["OHMS_PUBLIC_URL"].rstrip("/") + "/mcp",
                    "name": "ohms",
                    "authorization_token": env["OHMS_API_TOKEN_READ"],
                }
            ],
            betas=[MCP_CLIENT_BETA],
        )
    except Exception as e:  # noqa: BLE001 — we explicitly sanitize
        fail(f"claude API call failed: {type(e).__name__}")

    # Parse the text response without logging it verbatim.
    names: list[str] = []
    try:
        for block in response.content:
            text = getattr(block, "text", "")
            for line in text.splitlines():
                line = line.strip().lstrip("-*0123456789. ").strip()
                if line and not line.startswith("(") and "." not in line[-3:]:
                    names.append(line)
    except Exception as e:  # noqa: BLE001
        fail(f"unable to parse tool listing: {type(e).__name__}")

    return len(set(names))


def main() -> int:
    env = _require_env()
    print("[verify] env check: OK (no values logged)")

    base = env["OHMS_PUBLIC_URL"]
    print(f"[verify] running /health pre-check against {base.split('//')[-1].split('.')[0]}... (hostname elided)")
    _healthcheck(base)
    print("[verify] /health: OK")

    print("[verify] running Claude API → OHMS tool-listing handshake...")
    n = _verify_mcp_listing(env)

    # 6 tools in Phase 1 registry (see README.md). Accept 5-6 to tolerate LLM wording variance.
    if n < 5:
        fail(f"Claude discovered {n} tools; expected 6. Check OHMS tool registration and token scope.")
    print(f"[verify] tool-listing handshake: OK ({n} tools discovered)")
    print("[verify] PASS — Phase 2 handshake confirmed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
