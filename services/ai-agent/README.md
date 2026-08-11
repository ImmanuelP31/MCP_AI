# AI Agent Orchestrator

The AI agent orchestrator understands engineering intents, selects governed MCP tools, aggregates
results, and routes high-risk operations through the MCP gateway approval workflow.

The agent must not access PostgreSQL, Redis, Kafka, OpenSearch, simulator internals, shell
commands, SQL, or domain MCP dispatchers directly. Its execution boundary is the MCP gateway.

The current implementation includes a deterministic mock provider for repeatable tests. A future
LLM provider can replace the intent provider without changing gateway tool execution semantics.
