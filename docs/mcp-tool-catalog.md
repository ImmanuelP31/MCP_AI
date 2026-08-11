# MCP Tool Catalog

This catalog lists the MCP domain tools exposed by the separate domain servers. The MCP
gateway remains the policy enforcement point: tools require authenticated actor context,
permission checks, tool enabled checks, strict input validation, and structured error output.

No tool accepts arbitrary SQL, arbitrary shell commands, arbitrary URLs, or arbitrary file
paths. High-risk tools require an approved operation token supplied by the governance layer.
Timeout seconds and rate limits are enforced from the central tool registry metadata.

| Server | Tool | Risk | Permission | Approval | Description |
| --- | --- | --- | --- | --- | --- |
| device-mcp | list_devices | LOW | devices:read | No | List simulator devices with filters and pagination. |
| device-mcp | get_device | LOW | devices:read | No | Read full simulator device inventory details. |
| device-mcp | get_device_status | LOW | devices:read | No | Read current simulator device status. |
| device-mcp | get_device_health | LOW | devices:read | No | Read current simulator device health score and state. |
| device-mcp | get_device_telemetry | LOW | devices:read | No | Read recent simulator telemetry points. |
| device-mcp | get_device_configuration | LOW | devices:read | No | Read sanitized simulator runtime configuration. |
| device-mcp | get_device_services | LOW | devices:read | No | Read simulator device service states. |
| device-mcp | run_device_diagnostics | MEDIUM | devices:diagnose | No | Run bounded diagnostics on a simulator device. |
| device-mcp | restart_device | HIGH | devices:operate | Yes | Request a governed simulator device restart. |
| device-mcp | restart_service | HIGH | devices:operate | Yes | Request a governed service restart on a simulator device. |
| device-mcp | update_device_configuration | CRITICAL | devices:operate | Yes | Request a governed simulator device configuration update. |
| diagnostics-mcp | search_logs | LOW | devices:read | No | Search operational logs for simulator devices. |
| diagnostics-mcp | get_recent_errors | LOW | devices:read | No | Read recent operational errors for a simulator device. |
| diagnostics-mcp | get_error_details | LOW | devices:read | No | Read structured details for a known error code. |
| diagnostics-mcp | get_service_health | LOW | devices:read | No | Read diagnostic health for a specific device service. |
| diagnostics-mcp | get_resource_usage | LOW | devices:read | No | Read resource usage summary for a simulator device. |
| diagnostics-mcp | find_similar_incidents | LOW | devices:read | No | Find seeded historical incidents similar to a device failure. |
| diagnostics-mcp | run_diagnostic_check | MEDIUM | devices:diagnose | No | Run one bounded diagnostic check for a simulator device. |
| diagnostics-mcp | generate_diagnostic_summary | MEDIUM | devices:diagnose | No | Generate a structured diagnostic summary for a simulator device. |
| knowledge-mcp | search_knowledge | LOW | knowledge:read | No | Search seeded engineering knowledge documents. |
| knowledge-mcp | get_document | LOW | knowledge:read | No | Read a seeded engineering knowledge document. |
| knowledge-mcp | get_procedure | LOW | knowledge:read | No | Read a seeded troubleshooting or operations procedure. |
| knowledge-mcp | find_troubleshooting_steps | LOW | knowledge:read | No | Find troubleshooting steps for a known error code. |
| knowledge-mcp | search_configuration_guides | LOW | knowledge:read | No | Search seeded configuration guides. |
| ticket-mcp | create_ticket | MEDIUM | tickets:create | No | Create an engineering maintenance ticket. |
| ticket-mcp | get_ticket | LOW | tickets:read | No | Read an engineering maintenance ticket. |
| ticket-mcp | update_ticket | LOW | tickets:update | No | Update status, priority, or description on an engineering ticket. |
| ticket-mcp | assign_ticket | LOW | tickets:update | No | Assign an engineering maintenance ticket. |
| ticket-mcp | search_tickets | LOW | tickets:read | No | Search engineering maintenance tickets. |
| ticket-mcp | get_open_tickets | LOW | tickets:read | No | Read open engineering maintenance tickets. |

## Contract Coverage

The contract suite validates every tool for valid input, missing required fields, wrong data
types, unknown fields, device not found, permission denied, tool disabled, service unavailable,
and timeout.
