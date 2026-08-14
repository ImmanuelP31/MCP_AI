from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkflowStatus(StrEnum):
    PLANNED = "PLANNED"
    VALIDATED = "VALIDATED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkflowNodeStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    BLOCKED = "BLOCKED"
    DENIED = "DENIED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RetryStrategy(StrEnum):
    NO_RETRY = "NO_RETRY"
    FIXED_DELAY = "FIXED_DELAY"
    EXPONENTIAL_BACKOFF = "EXPONENTIAL_BACKOFF"


class PolicyDecision(StrEnum):
    ALLOW = "ALLOW"
    ALLOW_WITH_APPROVAL = "ALLOW_WITH_APPROVAL"
    DENY = "DENY"
    REQUIRE_ADDITIONAL_CONTEXT = "REQUIRE_ADDITIONAL_CONTEXT"


class ConditionOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    EXISTS = "exists"


class PlannerDecisionType(StrEnum):
    PLAN = "PLAN"
    CLARIFY = "CLARIFY"
    REFUSE = "REFUSE"


class WorkflowPolicyEvaluation(StrictModel):
    actor: str = Field(min_length=1, max_length=160)
    role: str = Field(min_length=1, max_length=64)
    tool: str = Field(min_length=1, max_length=128)
    resource: str | None = Field(default=None, max_length=240)
    environment: str = Field(min_length=1, max_length=64)
    risk: str = Field(min_length=1, max_length=32)
    decision: PolicyDecision
    policy_rule: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=500)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorkflowAuditEvent(StrictModel):
    event_type: str = Field(min_length=1, max_length=120)
    actor: str = Field(min_length=1, max_length=160)
    role: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=600)
    node_id: str | None = Field(default=None, max_length=120)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorkflowEdge(StrictModel):
    source: str = Field(min_length=1, max_length=120)
    destination: str = Field(min_length=1, max_length=120)
    condition: str | None = Field(default=None, max_length=300)


class ArgumentReference(StrictModel):
    argument: str = Field(min_length=1, max_length=120)
    source_node_id: str = Field(min_length=1, max_length=120)
    output_path: str = Field(min_length=1, max_length=240)


class WorkflowCondition(StrictModel):
    source_node_id: str = Field(min_length=1, max_length=120)
    output_path: str = Field(min_length=1, max_length=240)
    operator: ConditionOperator = ConditionOperator.EQ
    value: Any = None

    @field_validator("operator", mode="before")
    @classmethod
    def coerce_operator(cls, value: object) -> object:
        if isinstance(value, str):
            return ConditionOperator(value)
        return value


class WorkflowNode(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    workflow_id: UUID | None = None
    tool_name: str = Field(min_length=1, max_length=128)
    tool_server: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=500)
    arguments: dict[str, Any] = Field(default_factory=dict)
    argument_references: list[ArgumentReference] = Field(default_factory=list, max_length=20)
    depends_on: list[str] = Field(default_factory=list, max_length=20)
    condition: str | None = Field(default=None, max_length=300)
    typed_condition: WorkflowCondition | None = None
    risk_level: str = Field(min_length=1, max_length=32)
    approval_required: bool = False
    execution_status: WorkflowNodeStatus = WorkflowNodeStatus.PENDING
    attempts: int = Field(default=0, ge=0)
    max_retries: int = Field(default=0, ge=0, le=10)
    retry_strategy: RetryStrategy = RetryStrategy.NO_RETRY
    timeout_seconds: int = Field(default=30, ge=1, le=600)
    last_error: str | None = Field(default=None, max_length=600)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
    result_reference: str | None = Field(default=None, max_length=240)
    compensation_tool: str | None = Field(default=None, max_length=128)
    policy_evaluation: WorkflowPolicyEvaluation | None = None
    knowledge_references: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("depends_on")
    @classmethod
    def unique_dependencies(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("depends_on entries must be unique.")
        return value


class Workflow(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    user_request: str = Field(min_length=2, max_length=2000)
    status: WorkflowStatus = WorkflowStatus.PLANNED
    created_by: str = Field(min_length=1, max_length=160)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    target_environment: str = Field(default="dev", min_length=1, max_length=64)
    planner_model: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    version: int = Field(default=1, ge=1)
    nodes: list[WorkflowNode] = Field(default_factory=list, max_length=25)
    edges: list[WorkflowEdge] = Field(default_factory=list, max_length=50)
    original_plan: dict[str, Any] = Field(default_factory=dict)
    policy_transformed_plan: dict[str, Any] = Field(default_factory=dict)
    audit_events: list[WorkflowAuditEvent] = Field(default_factory=list, max_length=200)


class WorkflowPlanRequest(StrictModel):
    user_request: str = Field(min_length=2, max_length=2000)
    created_by: str = Field(default="api-user", min_length=1, max_length=160)
    role: str = Field(default="ENGINEER", min_length=1, max_length=64)
    target_environment: str = Field(default="dev", min_length=1, max_length=64)
    top_k: int = Field(default=8, ge=1, le=50)


class WorkflowPlanDraft(StrictModel):
    user_request: str = Field(min_length=2, max_length=2000)
    planner_model: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    nodes: list[WorkflowNode] = Field(default_factory=list, max_length=25)
    edges: list[WorkflowEdge] = Field(default_factory=list, max_length=50)
    planner_decision: PlannerDecisionType = PlannerDecisionType.PLAN
    reason: str | None = Field(default=None, max_length=500)
    missing_context: list[str] = Field(default_factory=list, max_length=10)


class WorkflowValidationIssue(StrictModel):
    code: str
    message: str
    node_id: str | None = None


class WorkflowPlanResult(StrictModel):
    workflow: Workflow
    validation_issues: list[WorkflowValidationIssue] = Field(default_factory=list)
    discovered_tools: list[dict[str, Any]] = Field(default_factory=list)
    capability_path: dict[str, Any] | None = None
    retrieved_knowledge: list[dict[str, Any]] = Field(default_factory=list)
    planner_provider: str = Field(default="deterministic", min_length=1, max_length=64)
    planner_model: str = Field(default="", max_length=120)
    embedding_provider: str = Field(default="unknown", min_length=1, max_length=64)
    retrieval_backend: str = Field(default="unknown", min_length=1, max_length=120)

    @property
    def ok(self) -> bool:
        return not self.validation_issues

    def as_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "workflow": self.workflow.model_dump(mode="json"),
            "validation_issues": [
                issue.model_dump(mode="json") for issue in self.validation_issues
            ],
            "discovered_tools": self.discovered_tools,
            "capability_path": self.capability_path,
            "retrieved_knowledge": self.retrieved_knowledge,
            "planner_provider": self.planner_provider,
            "planner_model": self.planner_model or self.workflow.planner_model,
            "embedding_provider": self.embedding_provider,
            "retrieval_backend": self.retrieval_backend,
        }
