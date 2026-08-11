from __future__ import annotations

from mcp.server.lowlevel import Server
from mcp_ops_mcp.dispatcher import McpToolDispatcher, ToolDefinition, build_lowlevel_server
from mcp_ops_mcp.schemas import (
    DeviceIdInput,
    DiagnosticCheckInput,
    ErrorDetailsInput,
    SearchLogsInput,
    ServiceHealthInput,
    StructuredOutput,
)
from mcp_ops_mcp.services import DiagnosticsDomainService
from mcp_ops_policy.tool_registry import TOOL_REGISTRY


def create_dispatcher(
    service: DiagnosticsDomainService | None = None,
    *,
    disabled_tools: set[str] | None = None,
    unavailable_tools: set[str] | None = None,
    timeout_tools: set[str] | None = None,
) -> McpToolDispatcher:
    service = service or DiagnosticsDomainService()
    tools = [
        ToolDefinition(
            TOOL_REGISTRY["search_logs"],
            SearchLogsInput,
            StructuredOutput,
            lambda model: service.search_logs(
                model.device_id,
                model.severity,
                model.query,
                model.limit,
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_recent_errors"],
            DeviceIdInput,
            StructuredOutput,
            lambda model: service.recent_errors(model.device_id),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_error_details"],
            ErrorDetailsInput,
            StructuredOutput,
            lambda model: service.error_details(model.error_code),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_service_health"],
            ServiceHealthInput,
            StructuredOutput,
            lambda model: service.service_health(model.device_id, model.service_name),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_resource_usage"],
            DeviceIdInput,
            StructuredOutput,
            lambda model: service.resource_usage(model.device_id),
        ),
        ToolDefinition(
            TOOL_REGISTRY["find_similar_incidents"],
            DeviceIdInput,
            StructuredOutput,
            lambda model: service.similar_incidents(model.device_id),
        ),
        ToolDefinition(
            TOOL_REGISTRY["run_diagnostic_check"],
            DiagnosticCheckInput,
            StructuredOutput,
            lambda model: service.run_check(model.device_id, model.check_name),
        ),
        ToolDefinition(
            TOOL_REGISTRY["generate_diagnostic_summary"],
            DeviceIdInput,
            StructuredOutput,
            lambda model: service.summary(model.device_id),
        ),
    ]
    return McpToolDispatcher(
        tools,
        disabled_tools=disabled_tools,
        unavailable_tools=unavailable_tools,
        timeout_tools=timeout_tools,
    )


def create_server(dispatcher: McpToolDispatcher | None = None) -> Server:
    return build_lowlevel_server("diagnostics-mcp", dispatcher or create_dispatcher())


server = create_server()

