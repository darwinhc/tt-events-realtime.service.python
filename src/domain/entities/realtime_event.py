"""Realtime event notification entity."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class RealtimeEvent(BaseModel):
    """A transport-neutral notification emitted after a domain change."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    event_id: Optional[int] = Field(default=None, gt=0)
    location_id: Optional[int] = Field(default=None, gt=0)
    payload: dict[str, Any]
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
