"""Unit tests for Bearer auth middleware (security review C1, C2)."""

import os
from unittest.mock import patch

import pytest


def _reload_auth():
    """Re-import auth after env changes so _TOKENS picks up fresh values."""
    import importlib

    import ohms.auth as auth_mod

    importlib.reload(auth_mod)
    return auth_mod


def test_scoped_tokens_load(monkeypatch):
    monkeypatch.setenv("OHMS_API_TOKEN_READ", "read-token-abc")
    monkeypatch.setenv("OHMS_API_TOKEN_WRITE", "write-token-xyz")
    monkeypatch.delenv("OHMS_API_TOKEN", raising=False)
    auth_mod = _reload_auth()
    scopes = {rec.scope for rec in auth_mod._TOKENS}
    assert scopes == {"read", "write"}


def test_legacy_single_token_mode(monkeypatch):
    monkeypatch.delenv("OHMS_API_TOKEN_READ", raising=False)
    monkeypatch.delenv("OHMS_API_TOKEN_WRITE", raising=False)
    monkeypatch.setenv("OHMS_API_TOKEN", "legacy-token-123")
    auth_mod = _reload_auth()
    # Legacy token is registered as BOTH read and write.
    scopes = {rec.scope for rec in auth_mod._TOKENS}
    assert scopes == {"read", "write"}


def test_match_token_accepts_valid_bearer(monkeypatch):
    monkeypatch.setenv("OHMS_API_TOKEN_READ", "abc123")
    monkeypatch.setenv("OHMS_API_TOKEN_WRITE", "def456")
    monkeypatch.delenv("OHMS_API_TOKEN", raising=False)
    auth_mod = _reload_auth()
    rec = auth_mod._match_token("Bearer abc123")
    assert rec is not None
    assert rec.scope == "read"


def test_match_token_rejects_missing_prefix(monkeypatch):
    monkeypatch.setenv("OHMS_API_TOKEN_READ", "abc123")
    monkeypatch.delenv("OHMS_API_TOKEN_WRITE", raising=False)
    monkeypatch.delenv("OHMS_API_TOKEN", raising=False)
    auth_mod = _reload_auth()
    assert auth_mod._match_token("abc123") is None
    assert auth_mod._match_token("") is None
    assert auth_mod._match_token("Bearer") is None


def test_match_token_rejects_wrong_value(monkeypatch):
    monkeypatch.setenv("OHMS_API_TOKEN_READ", "abc123")
    monkeypatch.delenv("OHMS_API_TOKEN_WRITE", raising=False)
    monkeypatch.delenv("OHMS_API_TOKEN", raising=False)
    auth_mod = _reload_auth()
    assert auth_mod._match_token("Bearer wrong-token") is None


def test_match_token_uses_constant_time_compare(monkeypatch):
    """Smoke test: _match_token must go through hmac.compare_digest.

    We can't easily measure timing in a unit test, but we can verify that the
    implementation calls hmac.compare_digest at least once per token record.
    """
    monkeypatch.setenv("OHMS_API_TOKEN_READ", "abc123")
    monkeypatch.setenv("OHMS_API_TOKEN_WRITE", "def456")
    monkeypatch.delenv("OHMS_API_TOKEN", raising=False)
    auth_mod = _reload_auth()
    with patch("ohms.auth.hmac.compare_digest", wraps=__import__("hmac").compare_digest) as spy:
        auth_mod._match_token("Bearer zzz999")
        # One call per configured token — never short-circuits.
        assert spy.call_count == len(auth_mod._TOKENS)
