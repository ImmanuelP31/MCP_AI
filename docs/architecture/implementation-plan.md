# Implementation Plan

## Current Phase: Phase 0 Foundation

Status: implemented as the initial repository baseline.

Delivered:

- monorepo structure
- architecture and security documentation
- ADRs for service boundaries, MCP governance, data stores, approvals, and audit
- shared RBAC, tool registry, event, approval, observability, and configuration contracts
- PostgreSQL schema baseline
- Docker Compose development infrastructure for PostgreSQL, Redis, Kafka, OpenSearch, Prometheus, and Grafana
- frontend shell with lint, test, and build scripts
- CI skeleton for Python, frontend, and Docker Compose validation

## Phase 1: Core Backend Foundation

Goals:

- convert the SQL baseline into SQLAlchemy models and Alembic revisions
- add dependency-injected FastAPI application modules
- implement RFC 7807-style errors
- implement auth context extraction and RBAC middleware
- expose `/health`, `/ready`, and `/metrics`
- add structured logging, request IDs, and correlation IDs
- add first integration test against PostgreSQL

Exit criteria:

- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy packages apps`
- Docker Compose config validation
- API container build verification after Dockerfiles are introduced

## Phase 2: Simulator Gateway and Device MCP

Goals:

- seed 50 deterministic devices
- implement controlled telemetry generation
- implement deterministic failure scenarios
- implement Device MCP read tools
- add MCP gateway validation for device read and diagnostic tools

Exit criteria:

- contract tests prove schemas, valid calls, invalid calls, and unauthorized calls
- simulator tests are deterministic
- no high-risk operation can execute without gateway approval context

## Phase 3: Diagnostics, Incidents, and Knowledge

Goals:

- add OpenSearch log indexing and search filters
- implement Diagnostics MCP tools
- implement Knowledge MCP repository abstraction and seeded documents
- implement incident correlation logic

Exit criteria:

- diagnostic and knowledge contract tests pass
- incident correlation unit tests cover service crash, CPU, memory, network, sensor, telemetry delay, and disk scenarios

## Phase 4: Tickets, Approvals, and Audit

Goals:

- implement Ticket MCP server
- implement approval state machine and expiry
- implement high-risk restart approval flow
- implement append-oriented audit logging

Exit criteria:

- high-risk operations create approval requests instead of executing
- requester cannot approve own operation
- expired approvals cannot execute
- denial and execution are audited

## Phase 5: Enterprise Frontend

Goals:

- build login, overview, device fleet, device details, diagnostics, incidents, tickets, knowledge, approval center, tool registry, audit explorer, system health, and settings pages
- add Playwright coverage for the three required E2E scenarios

Exit criteria:

- no generic chatbot-first interface
- high-risk operations show operation, target, risk, reason, requester, and approval status
- frontend lint, tests, build, and Playwright pass

## Phase 6: Production Hardening

Goals:

- service-to-service authentication
- bounded retries, timeouts, and circuit breakers
- Redis rate limiting and idempotency state
- Kafka idempotent consumers
- Grafana dashboards
- Docker build verification and security scanning

Exit criteria:

- CI blocks on lint, type check, unit tests, contract tests, integration tests, frontend tests, Docker builds, and security scan
- docs describe failure behavior for PostgreSQL, Redis, Kafka, OpenSearch, and MCP unavailability

