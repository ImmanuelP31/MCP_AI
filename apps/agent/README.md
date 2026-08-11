# AI Agent Orchestrator

The agent orchestrator will translate user intent into governed MCP tool requests. It must not directly access databases, infrastructure, shell commands, SQL, arbitrary URLs, arbitrary files, or policy definitions.

Phase 0 defines the service boundary only. Future phases will add:

- provider-neutral model interface
- mock/local model mode
- intent planner
- MCP gateway client
- explanation and response composer
- safety tests proving the agent cannot bypass MCP governance

