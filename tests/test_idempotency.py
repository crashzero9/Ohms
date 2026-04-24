"""
Tests for the idempotency cache used by `update_order_status`.

Covers:
  - UUIDv4 validation (accept/reject)
  - Cache hit returns previously stored value
  - Cache miss returns None
  - Distinct keys don't collide
"""

from __future__ import annotations

import uuid

import pytest

from ohms import idempotency


def test_valid_uuidv4_accepted():
    key = str(uuid.uuid4())
    assert idempotency.validate_key(key) == key.lower()


def test_uppercase_uuid_normalized():
    key = str(uuid.uuid4()).upper()
    assert idempotency.validate_key(key) == key.lower()


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not-a-uuid",
        "12345678-1234-1234-1234-123456789012",  # not v4 (version digit is 1)
        "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx",
    ],
)
def test_invalid_keys_rejected(bad):
    with pytest.raises(ValueError):
        idempotency.validate_key(bad)


def test_non_string_rejected():
    with pytest.raises(ValueError):
        idempotency.validate_key(None)  # type: ignore[arg-type]


def test_cache_miss_returns_none():
    key = str(uuid.uuid4())
    assert idempotency.get(key) is None


def test_cache_hit_returns_value():
    key = str(uuid.uuid4())
    idempotency.put(key, {"order_id": "42", "new_status": "ready"})
    assert idempotency.get(key) == {"order_id": "42", "new_status": "ready"}


def test_distinct_keys_do_not_collide():
    k1 = str(uuid.uuid4())
    k2 = str(uuid.uuid4())
    idempotency.put(k1, "one")
    idempotency.put(k2, "two")
    assert idempotency.get(k1) == "one"
    assert idempotency.get(k2) == "two"
