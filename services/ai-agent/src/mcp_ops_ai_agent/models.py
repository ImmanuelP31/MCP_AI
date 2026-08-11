from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class AgentIntent(StrEnum):
    ANSWER_QUESTION = "ANSWER_QUESTION"
    DIAGNOSE_UNHEALTHY_DEVICE = "DIAGNOSE_UNHEALTHY_DEVICE"
    FIND_PROCEDURE = "FIND_PROCEDURE"
    CREATE_TICKET = "CREATE_TICKET"
    REQUEST_SERVICE_RESTART = "REQUEST_SERVICE_RESTART"
    EXECUTE_APPROVED_RESTART = "EXECUTE_APPROVED_RESTART"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class Intent:
    intent: AgentIntent
    device_id: str | None = None
    service_name: str | None = None
    approval_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ToolCallPlan:
    tool_name: str
    arguments: dict[str, Any]
    auth_token: str
    approval_id: UUID | None = None
    idempotency_key: str = field(default_factory=lambda: f"agent-{uuid4()}")


@dataclass(frozen=True, slots=True)
class AgentTraceStep:
    tool_name: str
    decision: str
    ok: bool
    approval_id: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ToolSelection:
    tool_name: str
    reason: str
    confidence: float


@dataclass(frozen=True, slots=True)
class AgentResponse:
    ok: bool
    intent: AgentIntent
    message: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    approval_required: bool = False
    approval_id: UUID | None = None
    trace: list[AgentTraceStep] = field(default_factory=list)
    confidence: float = 0.0
    escalation_required: bool = False
    escalation_reason: str | None = None
    selected_tools: list[ToolSelection] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)

    def as_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "intent": self.intent.value,
            "message": self.message,
            "evidence": self.evidence,
            "data": self.data,
            "approval_required": self.approval_required,
            "approval_id": str(self.approval_id) if self.approval_id else None,
            "confidence": self.confidence,
            "escalation_required": self.escalation_required,
            "escalation_reason": self.escalation_reason,
            "selected_tools": [
                {
                    "tool_name": tool.tool_name,
                    "reason": tool.reason,
                    "confidence": tool.confidence,
                }
                for tool in self.selected_tools
            ],
            "citations": self.citations,
            "trace": [
                {
                    "tool_name": step.tool_name,
                    "decision": step.decision,
                    "ok": step.ok,
                    "approval_id": step.approval_id,
                    "error_code": step.error_code,
                }
                for step in self.trace
            ],
        }
