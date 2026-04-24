"""
Idempotency key cache (Phase 3 security review H-item).

`update_order_status` and other write tools accept an `idempotency_key`
(UUIDv4). Repeated calls with the same key in a 24h window return the
cached result instead of re-issuing the write.

Phase 1.5 upgrade path: Redis-backed cache when we move to multi-node.
"""

from __future__ import annotations

import threading
import time
import re
from typing import Any

_LOCK = threading.Lock()
_STORE: dict[str, tuple[float, Any]] = {}
_TTL_SECONDS = 60 * 60 * 24  # 24h

_UUIDV4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def validate_key(key: str) -> str:
    if not isinstance(key, str) or not _UUIDV4_RE.fullmatch(key):
        raise ValueError("idempotency_key must be a UUIDv4")
    return key.lower()


def get(key: str) -> Any | None:
    now = time.monotonic()
    with _LOCK:
        entry = _STORE.get(key)
        if entry is None:
            return None
        stamp, value = entry
        if now - stamp > _TTL_SECONDS:
            _STORE.pop(key, None)
            return None
        return value


def put(key: str, value: Any) -> None:
    now = time.monotonic()
    with _LOCK:
        _STORE[key] = (now, value)
        # Opportunistic GC: if store grows > 10_000 entries, prune expired.
        if len(_STORE) > 10_000:
            expired = [k for k, (t, _) in _STORE.items() if now - t > _TTL_SECONDS]
            for k in expired:
                _STORE.pop(k, None)
