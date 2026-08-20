from __future__ import annotations

from hmac import compare_digest
from typing import Annotated, Any
from uuid import UUID

from fastapi import Body, FastAPI, Header, HTTPException
from mcp_ops_api.db.session import create_database_engine, create_session_factory
from mcp_ops_common.config import get_settings
from mcp_ops_observability.fastapi import add_observability
from mcp_ops_observability.logging import configure_logging

from mcp_ops_mcp_gateway.auth import HmacJwtAuthenticator
from mcp_ops_mcp_gateway.models import GatewayToolRequest, GatewayToolResponse
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

    @app.post(
        "/api/v1/gateway/tools/call",
        response_model=GatewayToolResponse,
        tags=["gateway"],
    )
    def call_tool(
        request_payload: Annotated[dict[str, Any], Body()],
        x_service_token: Annotated[str | None, Header()] = None,
    ) -> GatewayToolResponse:
        _authorize_service(settings, x_service_token)
        request = _request_from_json(request_payload)
        return gateway_obj.call_tool(request)

    return app


def _authorize_service(settings: Any, token: str | None) -> None:
    expected = settings.service_auth_shared_secret
    if not token or not expected or not compare_digest(token, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid MCP gateway service credentials.",
        )


def _request_from_json(payload: dict[str, Any]) -> GatewayToolRequest:
    coerced = dict(payload)
    for key in ("approval_id", "correlation_id", "workflow_id"):
        if isinstance(coerced.get(key), str):
            coerced[key] = UUID(coerced[key])
    return GatewayToolRequest.model_validate(coerced)


app = create_app()
