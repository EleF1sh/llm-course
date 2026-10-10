from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

SENSITIVE_KEYS = {
    "ownerphone",
    "owner_phone",
    "owneraddr",
    "owner_addr",
    "chipno",
    "chip_no",
}

_PHONE_RE = re.compile(r"\b1\d{10}\b")


def _is_sensitive_key(key: str) -> bool:
    normalized = key.replace("-", "").replace("_", "").lower()
    return normalized in {
        "ownerphone",
        "owneraddr",
        "chipno",
    } or key.lower() in SENSITIVE_KEYS


def redact(value: Any) -> Any:
    """Recursively redact sensitive fields and obvious phone numbers."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if _is_sensitive_key(str(k)):
                out[k] = "***REDACTED***"
            else:
                out[k] = redact(v)
        return out
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _PHONE_RE.sub("***REDACTED***", value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        for key in ("tool_name", "params", "status", "duration_ms"):
            if hasattr(record, key):
                val = getattr(record, key)
                payload[key] = redact(val) if key == "params" else val
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("pet_hospital_mcp")
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False
    return logger
