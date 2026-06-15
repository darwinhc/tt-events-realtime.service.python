"""Event-update command DTO."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EventUpdate(BaseModel):
    """A partial event update; organizer and lifecycle fields are immutable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: Optional[str] = Field(default=None, max_length=250)
    scheduled_at: Optional[datetime] = None
    duration_in_minutes: Optional[int] = Field(default=None, gt=0)
    location_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value):
        """Trim a textual title before validating it."""
        if not isinstance(value, str):
            return value
        return value.strip()

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: Optional[str]) -> Optional[str]:
        """Reject empty titles, including explicit null values."""
        if value is None or not value:
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
            raise ValueError("Event datetime must include a timezone.")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_changes(self) -> "EventUpdate":
        """Require at least one valid mutable field."""
        if not self.model_fields_set:
            raise ValueError("At least one event field must be updated.")
        for field_name in (
            "title",
            "duration_in_minutes",
            "location_id",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null.")
        return self
