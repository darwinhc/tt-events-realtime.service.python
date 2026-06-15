"""Public event creation input without client-controlled identity."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..entities import Event, Location


class EventCreate(BaseModel):
    """Event creation fields supplied independently of authenticated identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(max_length=250)
    duration_in_minutes: int = Field(gt=0)
    location_id: Optional[int] = Field(default=None, gt=0)
    location: Optional[Location] = None
    scheduled_at: Optional[datetime] = None

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value):
        """Trim the event title before validation."""
        if not isinstance(value, str):
            return value
        return value.strip()

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        """Require a non-empty event title."""
        if not value:
            raise ValueError("Event title cannot be empty.")
        return value

    @field_validator("scheduled_at")
    @classmethod
    def normalize_datetime(
        cls,
        value: Optional[datetime],
    ) -> Optional[datetime]:
        """Require timezone information and normalize timestamps to UTC."""
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Event datetimes must include a timezone.")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_location(self) -> "EventCreate":
        """Require exactly one location representation."""
        if (self.location_id is None) == (self.location is None):
            raise ValueError(
                "Event must provide location_id or location, not both."
            )
        return self

    def to_event(self, organizer: str) -> Event:
        """Build the internal event entity using authenticated identity."""
        return Event(
            **self.model_dump(),
            organizer=organizer,
        )
