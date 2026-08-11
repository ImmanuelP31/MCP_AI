# Deployment

## Local Development

Use `infra/docker/docker-compose.dev.yml` for local infrastructure and application image
build validation.

```bash
docker compose -f infra/docker/docker-compose.dev.yml up --build
```

Application services exposed by the development compose file:

| Service | Port | Purpose |
| --- | --- | --- |
| `api` | `8000` | FastAPI platform API, health, readiness, metrics |
| `simulator-gateway` | `8001` | Deterministic simulator HTTP API |
| `mcp-gateway` | `8002` | MCP gateway health/readiness container |
| `frontend` | `8080` | Built React dashboard served by Nginx |

## Configuration

Configuration is loaded from environment variables through `packages/common`.

Secrets must come from environment variables or a Vault-compatible abstraction. Never commit real secrets.

## Production Direction

Production deployments should build service images independently and provide:

- PostgreSQL migrations before app startup
- production `ENVIRONMENT=production`
- signed enterprise JWT authentication configured with `JWT_ISSUER`, `JWT_AUDIENCE`, and a non-default `JWT_SECRET_KEY`
- service-to-service authentication
- SQL-backed gateway stores for approvals, approval events, audit records, idempotency keys, and rate limits
- resource limits
- health and readiness checks
- logs shipped to the enterprise log platform
- metrics scraped by Prometheus
- Grafana dashboards provisioned from `infra/grafana/provisioning/dashboards`
- W3C `traceparent`, request IDs, and correlation IDs propagated across service boundaries
- log redaction enabled for passwords, JWTs, API keys, database credentials, bearer tokens,
  cookies, and generic secret fields

Local validation of image builds requires Docker Desktop or another compatible Docker daemon.
GitHub Actions validation requires a committed repository pushed to a configured GitHub remote.
