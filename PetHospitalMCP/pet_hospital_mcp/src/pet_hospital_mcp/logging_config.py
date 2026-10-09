"""Structured JSON logging with recursive sensitive value masking."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Iterable

SENSITIVE_KEYS = frozenset(
    {
        "ownerphone",
        "owner_phone",
        "owneraddr",
        "owner_addr",
        "chipno",
        "chip_no",
    }
)

MASK = "***"
_PHONE_MASK = "***"

_PAYLOAD_KEY = "payload"


def is_sensitive(key: str) -> bool:
    return str(key).lower() in SENSITIVE_KEYS


def _mask_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return MASK
    if len(value) >= 7:
        return value[:3] + _PHONE_MASK + value[-2:]
    return MASK


def mask_sensitive(value: Any) -> Any:
    """Recursively mask sensitive values (phone / address / chip number)."""
    if isinstance(value, dict):
        return {
            key: (_mask_scalar(item) if is_sensitive(key) else mask_sensitive(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [mask_sensitive(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """One JSON object per log line; never serialises stack traces."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }
        extra = getattr(record, _PAYLOAD_KEY, None)
        if isinstance(extra, dict):
            payload.update(extra)
        else:
            payload["message"] = record.getMessage()
        if record.exc_info:
            exc_type = record.exc_info[0]
            payload["exception"] = getattr(exc_type, "__name__", "Exception")
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", stream: Any = None) -> logging.Logger:
    """Configure the package logger exactly once."""
    logger = logging.getLogger("pet_hospital_mcp")
    logger.setLevel(level.upper())
    logger.propagate = False
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler(stream or sys.stderr)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    logger = logging.getLogger("pet_hospital_mcp")
    if not logger.handlers:
        setup_logging()
    return logger


def log_event(level: int, payload: dict[str, Any]) -> None:
    logger = get_logger()
    logger.log(level, json.dumps(payload, ensure_ascii=False, default=str),
               extra={_PAYLOAD_KEY: payload})


def log_tool_call(
    tool_name: str,
    params: dict[str, Any] | None,
    status: str,
    duration_ms: float,
    *,
    level: int = logging.INFO,
    error_code: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit the audit record required for every tool invocation."""
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool_name": tool_name,
        "params": mask_sensitive(params or {}),
        "status": status,
        "duration_ms": round(duration_ms, 3),
    }
    if error_code:
        payload["error_code"] = error_code
    if extra:
        payload.update(mask_sensitive(extra))
    log_event(level, payload)


def safe_repr(values: Iterable[Any], limit: int = 200) -> str:
    text = ", ".join(str(v) for v in values)
    return text if len(text) <= limit else text[: limit - 1] + "…"
