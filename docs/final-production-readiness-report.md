# Final Production-Readiness Report

Date: 2026-08-18

## Measured Validation

| Check | Result |
| --- | --- |
| Backend tests | 404 passed |
| Frontend unit tests | 9 passed |
| Frontend lint | passed |
| Frontend TypeScript check | passed |
| Frontend production build | passed |
| Frontend E2E | 1 passed |
| Ruff | passed |
| mypy | passed, 160 source files |
| Bandit | no issues identified across 23,694 scanned LOC |
| Docker Compose config | passed; Docker emitted a local config-file access warning |
| Docker Compose startup | not rerun in this pass because Docker Engine access was denied from this session |
| Empty database migration | passed, upgraded to head |
| Previous schema migration | passed, `0004_workflow_resiliency` to head |

## Inventory

| Item | Measured Count |
| --- | ---: |
| FastAPI documented routes | 18 |
| Domain MCP servers | 4 |
| MCP gateway | 1 |
| Registered MCP tools | 52 |
| Alembic migrations | 5 |
| Evaluation scenarios | 330 |

## Latest Evaluation Metrics

Mock-mode baseline results are retained in historical artifacts for comparison. The tracked
`evaluation/results/latest.json` artifact currently reflects a live 50-case Gemini held-out run
with hashing retrieval.

| Configuration | Cases | Provider OK | Tool Recall | Tool Precision | Workflow Validity | Unknown/Disallowed Tool Rate | RAG Recall@K | Plan Acceptance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| semantic_rag_graph | 50 | 34 | 0.3358 | 0.3309 | 0.9118 | 0.0000 | 0.2059 | 0.8235 |

Provider-success quality metrics are computed over provider-successful cases only. End-to-end
workflow validity was `0.6200` because 16 cases returned Gemini HTTP `429`. This benchmark did not
execute MCP tools, so execution success is intentionally not claimed.

## Readiness Endpoints

The previous Docker readiness pass returned:

- API: `ready` with API, PostgreSQL, Redis, Kafka, OpenSearch, Device MCP, Diagnostics MCP, Knowledge MCP, Ticket MCP, and model provider components.
- MCP Gateway: `ready` with gateway, tool registry, approval store, and audit log components.
- Simulator Gateway: `ready` with registry, event bus, telemetry producer, and telemetry consumer components.

## Integration Findings

Implemented during this pass:

- API readiness now reports component-level dependency and MCP server state.
- MCP gateway and simulator gateway expose `/ready`.
- Docker Compose healthchecks cover API, MCP gateway, simulator, PostgreSQL, Redis, Kafka, and OpenSearch.
- API HTTP and validation errors return a consistent structured error schema.
- Workflow cancellation now records an audit event and honors actor role context.
- Frontend has an explicit `typecheck` script.
- Readiness HTTP probing now restricts checks to HTTP/HTTPS-only connections.

## Known Limitations

- Evaluation metrics are deterministic mock-mode metrics unless a live model provider is configured and a real benchmark is run.
- Local Docker Compose proves image build/startup and service health, but it is not a production orchestration design.
- The demo engineering corpus and simulator are synthetic.
- Enterprise OIDC/JWKS integration should be connected to the existing JWT authenticator boundary for a real company pilot.
- Live CI status in GitHub Actions was not measured in this local environment.
