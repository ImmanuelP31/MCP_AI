from __future__ import annotations

from fastapi import FastAPI
from mcp_ops_api.db.session import create_database_engine, create_session_factory
from mcp_ops_common.config import get_settings
from mcp_ops_observability.fastapi import add_observability
from mcp_ops_observability.logging import configure_logging

from mcp_ops_mcp_gateway.auth import HmacJwtAuthenticator
from mcp_ops_mcp_gateway.persistence import (
    SqlAlchemyApprovalStore,
    SqlAlchemyAuditLog,
    SqlAlchemyFixedWindowRateLimiter,
    SqlAlchemyIdempotencyStore,
)
from mcp_ops_mcp_gateway.service import McpGateway

configure_logging()


def create_app(gateway: McpGateway | None = None) -> FastAPI:
    settings = get_settings()
    gateway_obj = gateway
    if gateway_obj is None:
        if settings.environment == "production":
            engine = create_database_engine(settings)
            session_factory = create_session_factory(engine)
            gateway_obj = McpGateway(
                authenticator=HmacJwtAuthenticator(settings),
                rate_limiter=SqlAlchemyFixedWindowRateLimiter(session_factory),
                idempotency=SqlAlchemyIdempotencyStore(session_factory),
                approvals=SqlAlchemyApprovalStore(
                    session_factory,
                    ttl_seconds=settings.approval_ttl_seconds,
                ),
                audit_log=SqlAlchemyAuditLog(session_factory),
            )
        else:
            gateway_obj = McpGateway()
    app = FastAPI(
        title="MCP Gateway",
        version="0.1.0",
        docs_url="/gateway/docs",
        openapi_url="/gateway/openapi.json",
    )
    app.state.gateway = gateway_obj
    add_observability(app)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/ready", tags=["health"])
    def ready() -> dict[str, object]:
        return {
            "status": "ready",
            "components": {
                "gateway": {"status": "ready"},
                "tool_registry": {"status": "ready", "tools": len(gateway_obj.registry)},
                "approval_store": {"status": "ready"},
                "audit_log": {"status": "ready"},
            },
        }

    return app


app = create_app()
