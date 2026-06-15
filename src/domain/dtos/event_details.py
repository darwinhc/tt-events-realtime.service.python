"""Enriched event read model."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ..entities import Event, EventStatus, Location


class EventDetails(BaseModel):
    """An event enriched with location and participation information."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int = Field(gt=0)
    title: str
    organizer: str
    organizer_id: int = Field(gt=0)
    duration_in_minutes: int
    location_id: int = Field(gt=0)
    location: Location
    scheduled_at: Optional[datetime] = None
    status: EventStatus
    canceled_at: Optional[datetime] = None
    deletion_scheduled_at: Optional[datetime] = None
    joiners_count: int = Field(ge=0)

    @classmethod
    def from_event(
        cls,
        event: Event,
        location: Location,
        joiners_count: int,
    ) -> "EventDetails":
        """Build an enriched view from its source entities."""
        return cls(
            **event.model_dump(exclude={"location"}),
            location=location,
            joiners_count=joiners_count,
        )
