from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from mcp_ops_device_mcp.server import create_dispatcher as create_device_dispatcher
from mcp_ops_diagnostics_mcp.server import create_dispatcher as create_diagnostics_dispatcher
from mcp_ops_knowledge_mcp.server import create_dispatcher as create_knowledge_dispatcher
from mcp_ops_mcp.dispatcher import McpToolDispatcher
from mcp_ops_repository_mcp.server import create_dispatcher as create_repository_dispatcher
from mcp_ops_ticket_mcp.server import create_dispatcher as create_ticket_dispatcher

VALID_INPUTS: dict[str, dict[str, Any]] = {
    "list_devices": {"actor_role": "VIEWER", "limit": 2},
    "get_device": {"actor_role": "VIEWER", "device_id": "SIM-014"},
    "get_device_status": {"actor_role": "VIEWER", "device_id": "SIM-014"},
    "get_device_health": {"actor_role": "VIEWER", "device_id": "SIM-014"},
    "get_device_telemetry": {"actor_role": "VIEWER", "device_id": "SIM-014", "limit": 2},
    "get_device_configuration": {"actor_role": "VIEWER", "device_id": "SIM-014"},
    "get_device_services": {"actor_role": "VIEWER", "device_id": "SIM-014"},
    "run_device_diagnostics": {"actor_role": "ENGINEER", "device_id": "SIM-014"},
    "restart_device": {
        "actor_role": "OPERATOR",
        "device_id": "SIM-014",
        "approval_token": "APPROVED_OPERATION_TOKEN",  # nosec B105 - deterministic contract token.
        "reason": "Approved maintenance restart.",
    },
    "restart_service": {
        "actor_role": "OPERATOR",
        "device_id": "SIM-014",
        "service_name": "sensor-ingestor",
        "approval_token": "APPROVED_OPERATION_TOKEN",  # nosec B105 - deterministic contract token.
        "reason": "Approved service recovery.",
    },
    "update_device_configuration": {
        "actor_role": "OPERATOR",
        "device_id": "SIM-014",
        "approval_token": "APPROVED_OPERATION_TOKEN",  # nosec B105 - deterministic contract token.
        "reason": "Approved telemetry interval update.",
        "configuration_patch": {"telemetry_interval_seconds": 20},
    },
    "search_logs": {"actor_role": "VIEWER", "device_id": "SIM-014", "limit": 2},
    "get_recent_errors": {"actor_role": "VIEWER", "device_id": "SIM-014"},
    "get_error_details": {"actor_role": "VIEWER", "error_code": "E-SENSOR-INIT"},
    "get_service_health": {
        "actor_role": "VIEWER",
        "device_id": "SIM-014",
        "service_name": "sensor-ingestor",
    },
    "get_resource_usage": {"actor_role": "VIEWER", "device_id": "SIM-014"},
    "find_similar_incidents": {"actor_role": "VIEWER", "device_id": "SIM-014"},
    "run_diagnostic_check": {
        "actor_role": "ENGINEER",
        "device_id": "SIM-014",
        "check_name": "service_health",
    },
    "generate_diagnostic_summary": {"actor_role": "ENGINEER", "device_id": "SIM-014"},
    "search_knowledge": {"actor_role": "VIEWER", "query": "sensor"},
    "get_document": {"actor_role": "VIEWER", "document_id": "kb-sensor-init"},
    "get_procedure": {"actor_role": "VIEWER", "procedure_id": "kb-service-restart"},
    "find_troubleshooting_steps": {"actor_role": "VIEWER", "error_code": "E-SENSOR-INIT"},
    "search_configuration_guides": {"actor_role": "VIEWER", "query": "configuration"},
    "create_ticket": {
        "actor_role": "ENGINEER",
        "device_id": "SIM-014",
        "title": "Investigate SIM-014 telemetry timeout",
        "description": "Diagnostics show repeated timeout and sensor initialization failures.",
        "priority": "CRITICAL",
        "team": "Simulator Operations",
        "diagnostic_evidence": {"error_code": "E-SENSOR-INIT"},
    },
    "get_ticket": {"actor_role": "VIEWER", "ticket_id": "TCK-014"},
    "update_ticket": {"actor_role": "ENGINEER", "ticket_id": "TCK-014", "status": "IN_PROGRESS"},
    "assign_ticket": {
        "actor_role": "ENGINEER",
        "ticket_id": "TCK-014",
        "assignee": "operator@example.internal",
    },
    "search_tickets": {"actor_role": "VIEWER", "device_id": "SIM-014"},
    "get_open_tickets": {"actor_role": "VIEWER", "limit": 5},
    "get_recent_commits": {
        "actor_role": "ENGINEER",
        "repository": "ImmanuelP31/MCP_AI",
        "limit": 2,
    },
    "get_commit_history": {
        "actor_role": "ENGINEER",
        "repository": "ImmanuelP31/MCP_AI",
        "limit": 2,
    },
    "list_recent_commits": {
        "actor_role": "ENGINEER",
        "repository": "ImmanuelP31/MCP_AI",
        "limit": 2,
    },
    "get_commit_details": {
        "actor_role": "ENGINEER",
        "repository": "ImmanuelP31/MCP_AI",
        "sha": "abc1234",
    },
    "get_changed_files": {
        "actor_role": "ENGINEER",
        "repository": "ImmanuelP31/MCP_AI",
        "head": "abc1234",
    },
    "get_workflow_runs": {
        "actor_role": "ENGINEER",
        "repository": "ImmanuelP31/MCP_AI",
        "limit": 2,
    },
    "get_build_status": {"actor_role": "ENGINEER", "repository": "ImmanuelP31/MCP_AI"},
    "get_latest_failed_build": {"actor_role": "ENGINEER", "repository": "ImmanuelP31/MCP_AI"},
    "get_failed_jobs": {
        "actor_role": "ENGINEER",
        "repository": "ImmanuelP31/MCP_AI",
        "run_id": 9001,
    },
    "get_workflow_run_jobs": {
        "actor_role": "ENGINEER",
        "repository": "ImmanuelP31/MCP_AI",
        "run_id": 9001,
    },
    "get_job_logs": {
        "actor_role": "ENGINEER",
        "repository": "ImmanuelP31/MCP_AI",
        "job_id": 101,
    },
    "get_pipeline_logs": {
        "actor_role": "ENGINEER",
        "repository": "ImmanuelP31/MCP_AI",
        "job_id": 101,
    },
    "create_issue": {
        "actor_role": "ENGINEER",
        "repository": "ImmanuelP31/MCP_AI",
        "title": "Investigate failed GitHub Actions build",
        "body": "The governed workflow found a code-related build failure.",
        "labels": ["demo", "mcp"],
    },
    "rerun_workflow": {
        "actor_role": "ENGINEER",
        "repository": "ImmanuelP31/MCP_AI",
        "run_id": 9001,
        "approval_token": "APPROVED_OPERATION_TOKEN",  # nosec B105 - deterministic contract token.
        "reason": "Approved CI rerun after investigation.",
    },
}


def test_every_mcp_tool_has_strict_schema_description_and_structured_output() -> None:
    for dispatcher in _dispatchers():
        for tool in dispatcher.list_tools():
            assert tool.description
            assert tool.input_schema["type"] == "object"
            assert tool.output_schema is not None
            assert tool.output_schema["type"] == "object"
            assert tool.input_schema.get("additionalProperties") is False
            Draft202012Validator.check_schema(tool.input_schema)
            Draft202012Validator.check_schema(tool.output_schema)


@pytest.mark.parametrize("tool_name,payload", sorted(VALID_INPUTS.items()))
def test_mcp_tool_valid_input_succeeds(tool_name: str, payload: dict[str, Any]) -> None:
    result = _dispatcher_for(tool_name).call_tool(tool_name, payload)

    assert not result.is_error
    assert result.structured_content["ok"] is True
    assert "data" in result.structured_content


@pytest.mark.parametrize("tool_name,payload", sorted(VALID_INPUTS.items()))
def test_mcp_tool_missing_required_fields_fail(tool_name: str, payload: dict[str, Any]) -> None:
    required_payload = dict(payload)
    required_payload.pop("actor_role")

    result = _dispatcher_for(tool_name).call_tool(tool_name, required_payload)

    assert result.is_error
    assert result.structured_content["error"]["code"] == "validation_error"


@pytest.mark.parametrize("tool_name,payload", sorted(VALID_INPUTS.items()))
def test_mcp_tool_wrong_data_types_fail(tool_name: str, payload: dict[str, Any]) -> None:
    wrong_payload = dict(payload)
    wrong_payload["actor_role"] = 42

    result = _dispatcher_for(tool_name).call_tool(tool_name, wrong_payload)

    assert result.is_error
    assert result.structured_content["error"]["code"] == "validation_error"


@pytest.mark.parametrize("tool_name,payload", sorted(VALID_INPUTS.items()))
def test_mcp_tool_rejects_unknown_input_fields(tool_name: str, payload: dict[str, Any]) -> None:
    polluted_payload = dict(payload)
    polluted_payload["sql"] = "DROP TABLE devices"

    result = _dispatcher_for(tool_name).call_tool(tool_name, polluted_payload)

    assert result.is_error
    assert result.structured_content["error"]["code"] == "validation_error"


def test_device_not_found_is_structured_error() -> None:
    result = create_device_dispatcher().call_tool(
        "get_device",
        {"actor_role": "VIEWER", "device_id": "SIM-999"},
    )

    assert result.is_error
    assert result.structured_content["error"]["code"] == "device_not_found"


def test_permission_denied_is_structured_error() -> None:
    result = create_device_dispatcher().call_tool(
        "restart_service",
        {
            "actor_role": "VIEWER",
            "device_id": "SIM-014",
            "service_name": "sensor-ingestor",
            "approval_token": "APPROVED_OPERATION_TOKEN",  # nosec B105 - deterministic contract token.
            "reason": "Approved service recovery.",
        },
    )

    assert result.is_error
    assert result.structured_content["error"]["code"] == "permission_denied"


def test_tool_disabled_is_structured_error() -> None:
    result = create_device_dispatcher(disabled_tools={"get_device"}).call_tool(
        "get_device",
        {"actor_role": "VIEWER", "device_id": "SIM-014"},
    )

    assert result.is_error
    assert result.structured_content["error"]["code"] == "tool_disabled"


def test_service_unavailable_is_structured_error() -> None:
    result = create_device_dispatcher(unavailable_tools={"get_device"}).call_tool(
        "get_device",
        {"actor_role": "VIEWER", "device_id": "SIM-014"},
    )

    assert result.is_error
    assert result.structured_content["error"]["code"] == "service_unavailable"


def test_timeout_is_structured_error() -> None:
    result = create_device_dispatcher(timeout_tools={"get_device"}).call_tool(
        "get_device",
        {"actor_role": "VIEWER", "device_id": "SIM-014"},
    )

    assert result.is_error
    assert result.structured_content["error"]["code"] == "timeout"


def _dispatchers() -> list[McpToolDispatcher]:
    return [
        create_device_dispatcher(),
        create_diagnostics_dispatcher(),
        create_knowledge_dispatcher(),
        create_repository_dispatcher(),
        create_ticket_dispatcher(),
    ]


def _dispatcher_for(tool_name: str) -> McpToolDispatcher:
    factories: list[Callable[[], McpToolDispatcher]] = [
        create_device_dispatcher,
        create_diagnostics_dispatcher,
        create_knowledge_dispatcher,
        create_repository_dispatcher,
        create_ticket_dispatcher,
    ]
    for factory in factories:
        dispatcher = factory()
        if any(tool.name == tool_name for tool in dispatcher.list_tools()):
            return dispatcher
    raise AssertionError(f"No dispatcher found for {tool_name}")
