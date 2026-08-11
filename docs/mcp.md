# MCP

See [mcp-tool-catalog.md](mcp-tool-catalog.md) for the current domain tool catalog,
strict schema expectations, and security classification table.

## Governance

The MCP gateway is the policy enforcement point. Domain MCP servers expose domain tools, but the agent only calls the gateway. The gateway consults the central tool registry before execution.

The gateway never trusts authorization fields supplied in model-generated tool arguments.
Trusted role, permission, and approval context is derived from authentication and server-side
approval state.

Approval states are `PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`, `EXECUTED`, and `FAILED`.
Every approval transition emits an approval event and appends an audit record.

Diagnostics tools use deterministic rule-based correlation. They do not claim true ML
root-cause analysis.

## AI Agent Orchestration

The AI engineering agent understands bounded intents, selects MCP tools, executes multi-step
workflows, aggregates results, and requests human approval for high-risk operations. It
communicates with the platform only through the MCP gateway. It does not execute SQL, shell
commands, or direct calls to PostgreSQL, Redis, Kafka, OpenSearch, simulator internals, or
domain MCP dispatchers.

The current provider is deterministic for repeatable tests. A future LLM provider can replace
intent understanding without changing the governed gateway execution boundary.

Required metadata:

- tool name
- domain
- description
- risk level
- required permission
- approval requirement
- rate limit
- enabled flag

## Domain Servers

### Device MCP

Read tools:

- `list_devices`
- `get_device`
- `get_device_status`
- `get_device_health`
- `get_device_telemetry`
- `get_device_configuration`
- `get_device_services`
- `run_device_diagnostics`

High-risk tools:

- `restart_device`
- `restart_service`
- `update_device_configuration`

### Diagnostics MCP

- `search_logs`
- `get_recent_errors`
- `get_error_details`
- `get_service_health`
- `get_resource_usage`
- `find_similar_incidents`
- `run_diagnostic_check`
- `generate_diagnostic_summary`

### Knowledge MCP

- `search_knowledge`
- `get_document`
- `get_procedure`
- `find_troubleshooting_steps`
- `search_configuration_guides`

The Knowledge MCP server uses seeded fictional/demo engineering documentation only. Seeded
documents cover simulator maintenance, network troubleshooting, sensor troubleshooting,
service restart, configuration, and preventive maintenance. Search currently uses keyword
matching behind a repository/search-backend abstraction so semantic or vector search can be
introduced later without changing MCP tool input contracts.

### Ticket MCP

- `create_ticket`
- `get_ticket`
- `update_ticket`
- `assign_ticket`
- `search_tickets`
- `get_open_tickets`

## Contract Tests

Every tool must prove:

- schema exists
- valid calls succeed
- invalid arguments fail
- unauthorized calls fail
- high-risk calls require approval
