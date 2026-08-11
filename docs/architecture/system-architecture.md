# System Architecture Diagram

```mermaid
flowchart LR
    User["Human operator or engineer"]
    UI["React enterprise dashboard"]
    Agent["AI engineering agent\nmock mode for deterministic demo"]
    Gateway["MCP gateway\npolicy enforcement point"]
    DeviceMcp["device-mcp"]
    DiagnosticsMcp["diagnostics-mcp"]
    KnowledgeMcp["knowledge-mcp"]
    TicketMcp["ticket-mcp"]
    Simulator["simulator-gateway\n50 deterministic SIM devices"]
    EventBus["Kafka-compatible event stream\nin-memory bus in demo"]
    Processor["Telemetry consumer\nhealth, alert, incident rules"]
    Db["PostgreSQL domain model"]
    Redis["Redis\ncache and optional runtime acceleration"]
    Search["OpenSearch\nlogs and knowledge target"]
    Observability["JSON logs, metrics, traces, Grafana"]

    User --> UI
    User --> Agent
    UI --> Gateway
    Agent --> Gateway
    Gateway --> DeviceMcp
    Gateway --> DiagnosticsMcp
    Gateway --> KnowledgeMcp
    Gateway --> TicketMcp
    DeviceMcp --> Simulator
    DiagnosticsMcp --> Simulator
    DiagnosticsMcp --> Search
    KnowledgeMcp --> Search
    TicketMcp --> Db
    Simulator --> EventBus
    EventBus --> Processor
    Processor --> Db
    Processor --> Observability
    Gateway --> Redis
    Gateway --> Db
    Gateway --> Observability
```

## Demo Boundaries

The Phase 13 scripts run the same domain services and gateway policy code in process with
deterministic in-memory stores. Production-mode gateway startup wires signed JWT validation
and SQL-backed approval, audit, idempotency, and rate-limit stores. The production boundary
remains unchanged: production MCP tool calls must route through the MCP gateway.
