from __future__ import annotations

import io
import json
import logging

from fastapi.testclient import TestClient
from mcp_ops_api.main import app
from mcp_ops_mcp_gateway.models import GatewayToolRequest
from mcp_ops_mcp_gateway.service import McpGateway
from mcp_ops_observability.context import (
    reset_observability_context,
    set_observability_context,
)
from mcp_ops_observability.logging import REDACTED, JsonFormatter, sanitize_value
from mcp_ops_observability.metrics import metrics_response


def test_log_sanitization_redacts_secret_keys_and_patterns() -> None:
    payload = {
        "username": "operator",
        "password": "super-secret",  # nosec B105 - verifies log redaction.
        "nested": {
            "api_key": "api-key-value",
            "database_url": "postgresql://user:pass@db:5432/app",
        },
        "message": "authorization=Bearer abc.def token=raw-token jwt=header.payload.signature",
    }

    sanitized = sanitize_value(payload)
    encoded = json.dumps(sanitized)

    assert sanitized["password"] == REDACTED
    assert sanitized["nested"]["api_key"] == REDACTED
    assert sanitized["nested"]["database_url"] == REDACTED
    assert "super-secret" not in encoded
    assert "api-key-value" not in encoded
    assert "user:pass" not in encoded
    assert "raw-token" not in encoded
    assert "header.payload.signature" not in encoded


def test_json_formatter_includes_context_ids_and_sanitizes_message() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.observability")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    tokens = set_observability_context(
        request_id="req-1",
        correlation_id="corr-1",
        trace_id="0" * 32,
        span_id="1" * 16,
    )

    try:
        logger.info(
            "processing password=super-secret",
            extra={"authorization": "Bearer abc.def", "safe": "visible"},
        )
    finally:
        reset_observability_context(tokens)

    record = json.loads(stream.getvalue())
    assert record["request_id"] == "req-1"
    assert record["correlation_id"] == "corr-1"
    assert record["trace_id"] == "0" * 32
    assert record["span_id"] == "1" * 16
    assert record["authorization"] == REDACTED
    assert record["safe"] == "visible"
    assert "super-secret" not in json.dumps(record)


def test_api_observability_headers_and_metrics_endpoint() -> None:
    client = TestClient(app)

    response = client.get(
        "/health",
        headers={
            "x-request-id": "req-test",
            "x-correlation-id": "corr-test",
            "traceparent": "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
        },
    )
    metrics = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-test"
    assert response.headers["x-correlation-id"] == "corr-test"
    assert response.headers["traceparent"].startswith("00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-")
    assert metrics.status_code == 200
    assert "mcp_ops_api_requests_total" in metrics.text


def test_api_readiness_reports_component_statuses() -> None:
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ready", "degraded"}
    assert {"api", "postgresql", "redis", "kafka", "opensearch", "model_provider"}.issubset(
        payload["components"]
    )
    assert payload["components"]["api"]["status"] == "ready"


def test_mcp_gateway_records_authorization_failure_metrics() -> None:
    gateway = McpGateway()

    response = gateway.call_tool(
        GatewayToolRequest(
            auth_token="viewer-token",  # noqa: S106  # nosec B106 - deterministic test token.
            tool_name="restart_service",
            arguments={
                "device_id": "SIM-014",
                "service_name": "sensor-ingestor",
                "reason": "Viewer cannot operate devices.",
            },
            idempotency_key="observability-denied-1",
        )
    )
    metrics = metrics_response().decode()

    assert not response.ok
    assert response.error is not None
    assert response.error["code"] == "permission_denied"
    assert "mcp_ops_tool_authorization_failures_total" in metrics
    assert 'tool_name="restart_service"' in metrics


def test_mcp_gateway_audit_hashes_arguments_and_records_target_resource() -> None:
    gateway = McpGateway()

    response = gateway.call_tool(
        GatewayToolRequest(
            auth_token="ai-token",  # noqa: S106  # nosec B106 - deterministic test token.
            tool_name="get_device_health",
            arguments={"device_id": "SIM-014"},
            idempotency_key="audit-hash-target-1",
        )
    )

    assert response.ok
    record = gateway.audit_log.records[-1]
    assert record.tool_name == "get_device_health"
    assert record.target_resource == "SIM-014"
    assert record.argument_hash is not None
    assert len(record.argument_hash) == 64
    assert "SIM-014" not in record.argument_hash
