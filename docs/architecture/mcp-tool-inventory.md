# MCP Tool Inventory

The MCP gateway is the only production component allowed to route tool requests to domain
MCP servers. This inventory mirrors the central tool registry used by the gateway.

| Domain Server | Tool | Risk | Permission | Approval | Rate Limit | Timeout |
| --- | --- | --- | --- | --- | --- | --- |
| device-mcp | `list_devices` | LOW | `devices:read` | No | 120/minute | 5s |
| device-mcp | `get_device` | LOW | `devices:read` | No | 120/minute | 5s |
| device-mcp | `get_device_status` | LOW | `devices:read` | No | 120/minute | 5s |
| device-mcp | `get_device_health` | LOW | `devices:read` | No | 120/minute | 5s |
| device-mcp | `get_device_telemetry` | LOW | `devices:read` | No | 120/minute | 5s |
| device-mcp | `get_device_configuration` | LOW | `devices:read` | No | 120/minute | 5s |
| device-mcp | `get_device_services` | LOW | `devices:read` | No | 120/minute | 5s |
| device-mcp | `run_device_diagnostics` | MEDIUM | `devices:diagnose` | No | 20/minute | 5s |
| device-mcp | `restart_device` | HIGH | `devices:operate` | Yes | 5/minute | 10s |
| device-mcp | `restart_service` | HIGH | `devices:operate` | Yes | 5/minute | 10s |
| device-mcp | `update_device_configuration` | CRITICAL | `devices:operate` | Yes | 2/minute | 15s |
| diagnostics-mcp | `search_logs` | LOW | `devices:read` | No | 60/minute | 5s |
| diagnostics-mcp | `get_recent_errors` | LOW | `devices:read` | No | 60/minute | 5s |
| diagnostics-mcp | `get_error_details` | LOW | `devices:read` | No | 60/minute | 5s |
| diagnostics-mcp | `get_service_health` | LOW | `devices:read` | No | 60/minute | 5s |
| diagnostics-mcp | `get_resource_usage` | LOW | `devices:read` | No | 60/minute | 5s |
| diagnostics-mcp | `find_similar_incidents` | LOW | `devices:read` | No | 60/minute | 5s |
| diagnostics-mcp | `run_diagnostic_check` | MEDIUM | `devices:diagnose` | No | 20/minute | 5s |
| diagnostics-mcp | `generate_diagnostic_summary` | MEDIUM | `devices:diagnose` | No | 20/minute | 5s |
| knowledge-mcp | `search_knowledge` | LOW | `knowledge:read` | No | 60/minute | 5s |
| knowledge-mcp | `get_document` | LOW | `knowledge:read` | No | 60/minute | 5s |
| knowledge-mcp | `get_procedure` | LOW | `knowledge:read` | No | 60/minute | 5s |
| knowledge-mcp | `find_troubleshooting_steps` | LOW | `knowledge:read` | No | 60/minute | 5s |
| knowledge-mcp | `search_configuration_guides` | LOW | `knowledge:read` | No | 60/minute | 5s |
| ticket-mcp | `create_ticket` | MEDIUM | `tickets:create` | No | 30/minute | 5s |
| ticket-mcp | `get_ticket` | LOW | `tickets:read` | No | 60/minute | 5s |
| ticket-mcp | `update_ticket` | LOW | `tickets:update` | No | 60/minute | 5s |
| ticket-mcp | `assign_ticket` | LOW | `tickets:update` | No | 60/minute | 5s |
| ticket-mcp | `search_tickets` | LOW | `tickets:read` | No | 60/minute | 5s |
| ticket-mcp | `get_open_tickets` | LOW | `tickets:read` | No | 60/minute | 5s |

## Demo Tool Coverage

| Demo | Tools Exercised |
| --- | --- |
| Fleet monitoring | Dashboard route and telemetry snapshot |
| Incident investigation | `get_device_health`, `search_logs`, `get_device_telemetry`, `get_device_status`, `get_device_services`, `get_recent_errors`, `find_similar_incidents`, `run_diagnostic_check`, `generate_diagnostic_summary` |
| Knowledge-assisted diagnosis | `search_knowledge`, `get_procedure`, `find_troubleshooting_steps` |
| Ticket automation | `create_ticket` |
| High-risk operation | `restart_service`, approval APIs, `get_service_health` |
