from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from mcp_ops_auth.rbac import Role
from mcp_ops_policy.tool_registry import RiskLevel
from pydantic import BaseModel, ConfigDict, Field


class PrincipalType(StrEnum):
    HUMAN = "HUMAN"
    AI_AGENT = "AI_AGENT"
    SERVICE = "SERVICE"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class GatewayDecision(StrEnum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    PENDING_APPROVAL = "PENDING_APPROVAL"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Principal(StrictModel):
    principal_id: str
    role: Role
    principal_type: PrincipalType = PrincipalType.HUMAN


class GatewayToolRequest(StrictModel):
    auth_token: str = Field(min_length=8)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=160)
    approval_id: UUID | None = None
    correlation_id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID | None = None
    workflow_node_id: str | None = Field(default=None, max_length=120)


class GatewayToolResponse(StrictModel):
    ok: bool
    decision: GatewayDecision
    correlation_id: UUID
    data: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, str] | None = None


class ApprovalRecord(StrictModel):
    approval_id: UUID = Field(default_factory=uuid4)
    requester_id: str
    requester_type: PrincipalType
    tool_name: str
    arguments: dict[str, Any]
    risk_level: RiskLevel
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejected_by: str | None = None
    rejected_at: datetime | None = None
    executed_at: datetime | None = None
    failure_reason: str | None = None
    execution_result: dict[str, Any] | None = None
    workflow_id: UUID | None = None
    workflow_node_id: str | None = None
    arguments_hash: str | None = None
    approval_binding_hash: str | None = None
    version: int = 1


class AuditRecord(StrictModel):
    timestamp: datetime
    actor_id: str
    actor_role: Role
    tool_name: str
    correlation_id: UUID
    decision: GatewayDecision
    authorization_result: str
    risk_level: RiskLevel | None = None
    approval_status: ApprovalStatus | None = None
    execution_status: str
    result_summary: str
    argument_hash: str | None = None
    target_resource: str | None = None


class ApprovalEvent(StrictModel):
    event_id: UUID = Field(default_factory=uuid4)
    approval_id: UUID
    event_type: str
    timestamp: datetime
    actor_id: str
    status: ApprovalStatus
    tool_name: str
