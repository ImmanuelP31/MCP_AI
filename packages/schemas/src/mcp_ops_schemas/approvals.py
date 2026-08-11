from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ApprovalState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class ApprovalRequest(BaseModel):
    request_id: UUID
    requested_by: UUID
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any]
    target_device: str | None = None
    risk_level: str
    reason: str = Field(min_length=1)
    state: ApprovalState = ApprovalState.PENDING
    created_at: datetime
    expires_at: datetime
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    execution_result: dict[str, Any] | None = None
