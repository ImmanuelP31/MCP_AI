from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from mcp_ops_observability.context import (
    current_correlation_id,
    current_request_id,
    current_span_id,
    current_trace_id,
)

REDACTED = "<redacted>"
SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "token",
    "jwt",
    "password",
    "passwd",
    "pwd",
    "secret",
    "client_secret",
    "database_url",
    "database_password",
    "postgres_dsn",
    "redis_url",
    "cookie",
    "set_cookie",
    "credentials",
    "credential",
}
SECRET_PATTERNS = [
    re.compile(
        r"(?i)\b(password|passwd|pwd|api[_-]?key|access[_-]?token|refresh[_-]?token|"
        r"token|jwt|secret|client[_-]?secret|authorization)\s*[:=]\s*[^,\s]+"
    ),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(postgresql|postgres|redis)://[^:\s/@]+:[^@\s]+@"),
]
LOG_RECORD_RESERVED = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_value(record.getMessage()),
        }
        request_id = current_request_id()
        correlation_id = current_correlation_id()
        trace_id = current_trace_id()
        span_id = current_span_id()
        if request_id:
            payload["request_id"] = request_id
        if correlation_id:
            payload["correlation_id"] = correlation_id
        if trace_id:
            payload["trace_id"] = trace_id
        if span_id:
            payload["span_id"] = span_id
        if record.exc_info:
            payload["exception"] = sanitize_value(self.formatException(record.exc_info))
        payload.update(_extra_fields(record))
        return json.dumps(sanitize_value(payload), separators=(",", ":"), sort_keys=True)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _is_sensitive_key(str(key)) else sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple | set):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value)
    return value


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: sanitize_value(value)
        for key, value in record.__dict__.items()
        if key not in LOG_RECORD_RESERVED and not key.startswith("_")
    }


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in SENSITIVE_KEYS or any(part in normalized for part in SENSITIVE_KEYS)


def _sanitize_string(value: str) -> str:
    sanitized = value
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub(_redact_match, sanitized)
    return sanitized


def _redact_match(match: re.Match[str]) -> str:
    text = match.group(0)
    if text.lower().startswith("bearer"):
        return "Bearer " + REDACTED
    if "://" in text and "@" in text:
        scheme = text.split("://", maxsplit=1)[0]
        return f"{scheme}://{REDACTED}:{REDACTED}@"
    separator = ":" if ":" in text and "=" not in text else "="
    key = text.split(separator, maxsplit=1)[0].strip()
    return f"{key}{separator}{REDACTED}"
