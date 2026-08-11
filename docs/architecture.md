# Architecture

## Purpose

The platform is an Enterprise AI Engineering Control Plane: a governed layer that lets engineers ask natural-language questions and request engineering actions while preserving MCP tool boundaries, policy enforcement, human approvals, auditability, and observability.

## Runtime Components

```mermaid
flowchart TB
    Frontend["React Dashboard"] --> API["FastAPI API"]
    API --> Agent["AI Agent / Planner"]
    Agent --> Discovery["Semantic Tool Discovery"]
    Agent --> RAG["Engineering Knowledge RAG"]
    Agent --> Workflows["Workflow DAG Service"]
    Workflows --> Capability["Capability Graph"]
    Workflows --> Policy["RBAC / Policy"]
    Workflows --> Approval["Approval Workflow"]
    Workflows --> Gateway["MCP Gateway"]
    Gateway --> DeviceMCP["Device MCP"]
    Gateway --> DiagnosticsMCP["Diagnostics MCP"]
    Gateway --> KnowledgeMCP["Knowledge MCP"]
    Gateway --> TicketMCP["Ticket MCP"]
    Gateway --> Audit["Audit Store"]
    DeviceMCP --> Simulator["Simulator Gateway"]
    Simulator --> Kafka["Kafka"]
    API --> Postgres["PostgreSQL"]
    API --> Redis["Redis"]
    RAG --> OpenSearch["OpenSearch"]
    API --> Prometheus["Prometheus"]
    Prometheus --> Grafana["Grafana"]
```

## Request Flow

```mermaid
sequenceDiagram
    participant User
    participant UI as React UI
    participant API
    participant Disc as Tool Discovery
    participant RAG
    participant Planner
    participant Policy
    participant Approval
    participant MCP as MCP Gateway
    participant Audit

    User->>UI: Natural-language engineering request
    UI->>API: Authenticated request
    API->>Disc: Retrieve relevant tools
    Disc-->>API: Policy-filtered top-K tools
    API->>RAG: Retrieve engineering context
    RAG-->>API: Cited evidence
    API->>Planner: Build typed workflow DAG
    Planner-->>API: Proposed workflow
    API->>Policy: Validate and transform workflow
    Policy-->>API: Allow / approval / deny decisions
    alt approval required
        API->>Approval: Create bound approval request
        Approval-->>API: Pending
    else executable
        API->>MCP: Execute registered MCP tool
        MCP->>Audit: Record decision and result
        MCP-->>API: Structured result
    end
    API-->>UI: Workflow, status, evidence, audit references
```

## Data Architecture

PostgreSQL is the source of truth for the domain schema, workflow persistence, gateway persistence, audit, approvals, idempotency, and rate limits. Alembic owns schema evolution; application startup does not use `create_all()`.

Redis is used for runtime acceleration where available. Kafka carries telemetry and workflow-style events. OpenSearch backs engineering knowledge/log retrieval with deterministic local fallbacks for tests and degraded mode. Prometheus scrapes API and service metrics, and Grafana provides dashboards.

## MCP Boundary

Domain MCP servers expose typed tools. The MCP gateway is the only production routing point for tool execution. Tools are registered with normalized metadata: server, category, description, risk, permissions, roles, schema, tags, resource types, retry/idempotency settings, and optional compensation.

## Health And Readiness

Readiness checks now cover:

- API process
- PostgreSQL
- Redis
- Kafka
- OpenSearch
- Device MCP
- Diagnostics MCP
- Knowledge MCP
- Ticket MCP
- model provider configuration
- MCP gateway registry/stores
- simulator registry and event processors

Docker Compose healthchecks validate API, gateway, simulator, PostgreSQL, Redis, Kafka, and OpenSearch.

## Backward Compatibility

Direct tool calls still flow through the existing MCP gateway contract. New AI workflow functionality adds typed planning, policy transformation, capability guidance, RAG evidence, and recovery around the gateway rather than replacing it.
