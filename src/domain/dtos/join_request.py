"""Join-event command DTO using authenticated identity."""

from pydantic import BaseModel, ConfigDict, Field


class JoinEventRequest(BaseModel):
    """Event identifier supplied when the current user joins."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: int = Field(gt=0)
