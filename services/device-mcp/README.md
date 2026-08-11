# Device MCP Server

Owns device inventory, status, health, telemetry, configuration, services, diagnostics, and governed operational actions for simulator devices.

High-risk tools such as `restart_device`, `restart_service`, and `update_device_configuration` must never execute unless the MCP gateway provides an approved operation token.

