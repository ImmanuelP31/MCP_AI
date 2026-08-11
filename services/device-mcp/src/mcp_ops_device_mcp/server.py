from __future__ import annotations

from mcp.server.lowlevel import Server
from mcp_ops_mcp.dispatcher import McpToolDispatcher, ToolDefinition, build_lowlevel_server
from mcp_ops_mcp.schemas import (
    DeviceConfigurationInput,
    DeviceIdInput,
    DeviceTelemetryInput,
    PaginationInput,
    RestartDeviceInput,
    RestartServiceInput,
    RunDiagnosticsInput,
    StructuredOutput,
    UpdateDeviceConfigurationInput,
)
from mcp_ops_mcp.services import DeviceDomainService
from mcp_ops_policy.tool_registry import TOOL_REGISTRY


def create_dispatcher(
    service: DeviceDomainService | None = None,
    *,
    disabled_tools: set[str] | None = None,
    unavailable_tools: set[str] | None = None,
    timeout_tools: set[str] | None = None,
) -> McpToolDispatcher:
    service = service or DeviceDomainService()
    tools = [
        ToolDefinition(
            TOOL_REGISTRY["list_devices"],
            PaginationInput,
            StructuredOutput,
            lambda model: service.list_devices(model.limit),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_device"],
            DeviceIdInput,
            StructuredOutput,
            lambda model: service.get_device(model.device_id),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_device_status"],
            DeviceIdInput,
            StructuredOutput,
            lambda model: service.get_status(model.device_id),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_device_health"],
            DeviceIdInput,
            StructuredOutput,
            lambda model: service.get_health(model.device_id),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_device_telemetry"],
            DeviceTelemetryInput,
            StructuredOutput,
            lambda model: service.get_telemetry(model.device_id, model.limit),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_device_configuration"],
            DeviceConfigurationInput,
            StructuredOutput,
            lambda model: service.get_configuration(model.device_id),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_device_services"],
            DeviceIdInput,
            StructuredOutput,
            lambda model: service.get_services(model.device_id),
        ),
        ToolDefinition(
            TOOL_REGISTRY["run_device_diagnostics"],
            RunDiagnosticsInput,
            StructuredOutput,
            lambda model: service.run_diagnostics(model.device_id, model.checks),
        ),
        ToolDefinition(
            TOOL_REGISTRY["restart_device"],
            RestartDeviceInput,
            StructuredOutput,
            lambda model: service.restart_device(model.device_id, model.reason),
        ),
        ToolDefinition(
            TOOL_REGISTRY["restart_service"],
            RestartServiceInput,
            StructuredOutput,
            lambda model: service.restart_service(
                model.device_id,
                model.service_name,
                model.reason,
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["update_device_configuration"],
            UpdateDeviceConfigurationInput,
            StructuredOutput,
            lambda model: service.update_configuration(
                model.device_id,
                model.configuration_patch,
                model.reason,
            ),
        ),
    ]
    return McpToolDispatcher(
        tools,
        disabled_tools=disabled_tools,
        unavailable_tools=unavailable_tools,
        timeout_tools=timeout_tools,
    )


def create_server(dispatcher: McpToolDispatcher | None = None) -> Server:
    return build_lowlevel_server("device-mcp", dispatcher or create_dispatcher())


server = create_server()
