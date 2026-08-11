# MCP Gateway

The MCP gateway is the only path from the agent to domain MCP tools. It enforces authentication context, RBAC, policy, tool registry metadata, rate limits, approval workflow, idempotency, and audit recording.

Implemented governance controls:

- central tool registry lookup with risk, permission, approval, timeout, rate limit, and enabled metadata
- production-mode HS256 enterprise JWT authentication into trusted principals
- RBAC permission checks from server-side identity only
- model-supplied `actor_role`, `approval_token`, `risk_level`, and `required_permission` are stripped
- policy routing for approval-required tools
- fixed-window rate limiting with in-memory and SQLAlchemy-backed stores
- timeout enforcement
- correlation IDs on every request/response
- append-only audit records with in-memory and SQLAlchemy-backed stores
- idempotency-key duplicate rejection with in-memory and SQLAlchemy-backed stores
- approval creation, approval execution routing, expiry, and self-approval prevention
- approval listing, details, approval, rejection, execution, failure, and expiration state transitions
- transition events for `approval.requested`, `approval.approved`, `approval.rejected`, `approval.expired`, `approval.executed`, and `approval.failed`
- concurrency-safe approval state changes guarded by a lock and version counter

The gateway routes to the domain MCP dispatchers internally. Production agent calls should never target `device-mcp`, `diagnostics-mcp`, `knowledge-mcp`, or `ticket-mcp` directly.

In `ENVIRONMENT=production`, `create_app()` wires the JWT authenticator and SQLAlchemy-backed approval, audit, idempotency, and rate-limit stores. The application must run migrations before startup; it must not rely on `SQLAlchemy.create_all()` as an application startup path.

Demo:

```powershell
python scripts\demo_approval_workflow.py
```
