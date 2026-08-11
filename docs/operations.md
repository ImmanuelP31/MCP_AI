# Operations

## Health

Services expose:

- `/health` for liveness
- `/ready` for dependency readiness
- `/metrics` for Prometheus

Readiness must distinguish PostgreSQL, Redis, Kafka, and OpenSearch failures.

## Failure Handling

Use bounded retries, exponential backoff, timeouts, idempotency keys, and circuit breakers where appropriate.

No service should use infinite retries.

## Diagnostics

The diagnostics engine starts with deterministic, rule-based incident correlation. It does
not claim machine-learning root-cause analysis. Rules correlate telemetry, recent errors,
service state, and historical incident signals into structured diagnostic reports.

Example rules:

- packet loss plus network timeout errors indicates a network communication issue
- CPU saturation plus process response latency evidence indicates a CPU saturation candidate
- crashed service plus crash logs indicates a service failure candidate
- delayed telemetry indicates a telemetry delay
- disk usage above threshold indicates a disk capacity warning

Reports include diagnostic ID, device ID, timestamp, severity, observations, evidence,
possible causes, recommended actions, confidence, related incidents, and a diagnostic
timeline. Diagnostic responses also include citations to the seeded fictional engineering
knowledge documents that support matched deterministic rules.

## Knowledge System

The engineering knowledge system starts with keyword/full-text search over fictional/demo
documents. These documents are not actual company documentation. Seeded content includes:

- simulator maintenance manual
- network troubleshooting guide
- sensor troubleshooting guide
- service restart procedure
- configuration guide
- preventive maintenance SOP

Each document includes document ID, title, document type, version, device model, tags,
created timestamp, and updated timestamp. The repository delegates search to a backend
interface so semantic or vector retrieval can be added later without changing MCP tool
contracts.

## Observability

Required signals:

- structured JSON logs
- request IDs
- correlation IDs
- OpenTelemetry-compatible traces
- Prometheus metrics
- Grafana dashboards

Implemented observability primitives live in `packages/observability`:

- JSON logs include timestamp, level, logger, message, request ID, correlation ID, trace ID,
  and span ID.
- `x-request-id`, `x-correlation-id`, and W3C `traceparent` are accepted and propagated by
  FastAPI middleware.
- Trace IDs and span IDs are OpenTelemetry-compatible and emitted in logs.
- Prometheus metrics are exposed at `/metrics` for API, MCP gateway, and simulator gateway
  services.
- Grafana dashboards are provisioned from `infra/grafana/provisioning/dashboards`.

Tracked metrics:

- `mcp_ops_api_latency_seconds`
- `mcp_ops_api_requests_total`
- `mcp_ops_api_errors_total`
- `mcp_ops_mcp_calls_total`
- `mcp_ops_mcp_failures_total`
- `mcp_ops_tool_latency_seconds`
- `mcp_ops_tool_authorization_failures_total`
- `mcp_ops_approval_latency_seconds`
- `mcp_ops_device_health_score`
- `mcp_ops_kafka_consumer_lag`
- `mcp_ops_database_latency_seconds`
- `mcp_ops_redis_latency_seconds`
- `mcp_ops_opensearch_latency_seconds`

Log sanitization redacts secret values from structured fields and raw log messages. Logs must
not expose passwords, JWTs, API keys, database credentials, bearer tokens, cookies, or generic
secret fields.
