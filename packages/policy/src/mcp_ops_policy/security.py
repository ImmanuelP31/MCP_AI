from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any

from mcp_ops_observability.logging import sanitize_value
from mcp_ops_observability.metrics import (
    record_prompt_injection_detection,
    record_tool_metadata_rejection,
)

TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,127}$")
SERVER_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,127}$")
SUSPICIOUS_INSTRUCTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+(instructions|policy|rules)", re.IGNORECASE),
    re.compile(r"send\s+all\s+(credentials|secrets|tokens|passwords)", re.IGNORECASE),
    re.compile(r"reveal\s+(credentials|secrets|tokens|passwords)", re.IGNORECASE),
    re.compile(r"bypass\s+(policy|approval|authorization|rbac|gateway)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(admin|root|system)", re.IGNORECASE),
    re.compile(r"developer\s+message|system\s+prompt|hidden\s+instructions", re.IGNORECASE),
]
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ServerTrustLevel(StrEnum):
    CORE = "CORE"
    INTERNAL = "INTERNAL"
    PARTNER = "PARTNER"
    UNTRUSTED = "UNTRUSTED"


class ToolMetadataSecurityError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def sanitize_description(description: str) -> str:
    sanitized = CONTROL_CHARS.sub(" ", description).strip()
    return re.sub(r"\s+", " ", sanitized)[:600]


def suspicious_instruction_flags(text: str) -> list[str]:
    return [pattern.pattern for pattern in SUSPICIOUS_INSTRUCTION_PATTERNS if pattern.search(text)]


def detect_prompt_injection(text: str, *, source: str) -> bool:
    detected = bool(suspicious_instruction_flags(text))
    if detected:
        record_prompt_injection_detection(source=source)
    return detected


def validate_tool_identity(tool_name: str, server: str) -> None:
    if not TOOL_NAME_PATTERN.match(tool_name):
        record_tool_metadata_rejection(reason="invalid_tool_name")
        raise ToolMetadataSecurityError("invalid_tool_name")
    if not SERVER_NAME_PATTERN.match(server):
        record_tool_metadata_rejection(reason="invalid_server_name")
        raise ToolMetadataSecurityError("invalid_server_name")


def validate_tool_schema(schema: dict[str, Any]) -> None:
    if schema.get("type") != "object":
        record_tool_metadata_rejection(reason="invalid_input_schema")
        raise ToolMetadataSecurityError("invalid_input_schema")
    if schema.get("additionalProperties") is not False:
        record_tool_metadata_rejection(reason="permissive_input_schema")
        raise ToolMetadataSecurityError("permissive_input_schema")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        record_tool_metadata_rejection(reason="invalid_schema_properties")
        raise ToolMetadataSecurityError("invalid_schema_properties")


def fingerprint_metadata(payload: dict[str, Any]) -> str:
    stable_payload = {
        key: payload.get(key)
        for key in [
            "tool_name",
            "domain",
            "description",
            "risk_level",
            "required_permission",
            "requires_approval",
            "server",
            "category",
            "required_roles",
            "executable",
            "enabled",
        ]
    }
    encoded = json.dumps(stable_payload, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def hash_arguments(arguments: dict[str, Any]) -> str:
    sanitized = sanitize_value(arguments)
    encoded = json.dumps(sanitized, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def wrap_untrusted_tool_output(
    *,
    tool_name: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    serialized = json.dumps(data, default=str, sort_keys=True)[:10000]
    injection_detected = detect_prompt_injection(serialized, source="tool_output")
    return {
        "classification": "UNTRUSTED_TOOL_OUTPUT",
        "tool_name": tool_name,
        "prompt_injection_detected": injection_detected,
        "data": sanitize_value(data),
    }
