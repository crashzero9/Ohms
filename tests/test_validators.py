"""Unit tests for input validators (security review C4, M2)."""

import pytest

from ohms.validators import (
    ValidationError,
    validate_order_id,
    validate_printer_ip,
    validate_status,
)


@pytest.mark.parametrize("good", ["123456", "987654321", "5555555555555"])
def test_order_id_accepts_valid_digits(good):
    assert validate_order_id(good) == good


@pytest.mark.parametrize("bad", [
    "12345",                 # too short
    "1" * 21,                # too long
    "12345a",                # non-digit
    "123-456",               # dash
    "../etc/passwd",         # path traversal attempt
    "1?fields=foo",          # query injection attempt
    "",                      # empty
])
def test_order_id_rejects_bad(bad):
    with pytest.raises(ValidationError):
        validate_order_id(bad)


def test_order_id_rejects_non_string():
    with pytest.raises(ValidationError):
        validate_order_id(12345)  # type: ignore[arg-type]


@pytest.mark.parametrize("good", [
    "pending", "preparing", "ready_for_pickup", "out_for_delivery",
    "delivered", "cancelled", "refunded", "issue_flagged",
])
def test_status_accepts_allowlist(good):
    assert validate_status(good) == good


@pytest.mark.parametrize("bad", ["DROP TABLE", "admin", "PENDING", ""])
def test_status_rejects_others(bad):
    with pytest.raises(ValidationError):
        validate_status(bad)


@pytest.mark.parametrize("good", ["10.0.0.5", "192.168.1.42", "172.16.2.3"])
def test_printer_ip_accepts_rfc1918(good):
    assert validate_printer_ip(good) == good


@pytest.mark.parametrize("bad", [
    "8.8.8.8",           # public DNS
    "169.254.169.254",   # link-local / IMDS
    "127.0.0.1",         # loopback — reject (SSRF to localhost services)
    "notanip",
    "",
])
def test_printer_ip_rejects_public_and_garbage(bad):
    with pytest.raises(ValidationError):
        validate_printer_ip(bad)
