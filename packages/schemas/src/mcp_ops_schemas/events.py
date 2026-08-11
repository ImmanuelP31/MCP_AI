from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DomainEvent(BaseModel):
    event_id: UUID
    event_type: str = Field(min_length=1)
    timestamp: datetime
    source: str = Field(min_length=1)
    correlation_id: UUID
    actor_id: UUID | None = None
    payload: dict[str, Any]
    schema_version: str = "1.0"
