"""
Structured logging with secret + PII redaction.

Security review fixes:
  H4 — redact Authorization header and Shopify tokens from logs
  M3 — structured JSON logs with correlation IDs

Call `configure_logging()` once at process start (main.py does this first).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from logging.config import dictConfig

_SECRET_HEADER_NAMES = {
    "authorization",
    "x-shopify-access-token",
    "cookie",
    "set-cookie",
}

# Known PII field names in Shopify order payloads.
_PII_FIELDS = {
    "email", "phone", "customer_email", "billing_address",
    "shipping_address", "name", "first_name", "last_name",
}

_TOKEN_LIKE = re.compile(r"\b[a-fA-F0-9]{32,}\b|\bshpat_[A-Za-z0-9]+\b|\bBearer\s+\S+\b")


def _scrub(value):
    """Recursively scrub a dict/list/string for obvious secrets & PII."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            kl = k.lower() if isinstance(k, str) else k
            if isinstance(kl, str) and (kl in _SECRET_HEADER_NAMES or kl in _PII_FIELDS):
                out[k] = "[REDACTED]"
            else:
                out[k] = _scrub(v)
        return out
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, str):
        return _TOKEN_LIKE.sub("[REDACTED_TOKEN]", value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Attach any structured extras (dict passed via `extra=` kwarg).
        for attr, val in record.__dict__.items():
            if attr in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "message", "module",
                "msecs", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName",
            }:
                continue
            base[attr] = _scrub(val)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, default=str)


def configure_logging() -> None:
    level = os.environ.get("OHMS_LOG_LEVEL", "INFO").upper()
    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {"()": JsonFormatter},
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "json",
            },
        },
        "loggers": {
            "": {"handlers": ["stdout"], "level": level},
            # uvicorn emits its own access log we don't want (H4 fix).
            "uvicorn.access": {"handlers": [], "propagate": False, "level": "WARNING"},
        },
    })
