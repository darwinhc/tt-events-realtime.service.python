"""Event entity."""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from src.domain.exceptions import DomainValidationError

from .location import Location


class EventStatus(str, Enum):
    """Supported event lifecycle states."""

    ACTIVE = "active"
    CANCELED = "canceled"


class Event(BaseModel):
    """A scheduled or date-to-be-defined event."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "title": "Realtime Systems Meetup",
                    "organizer": "darwin",
                    "scheduled_at": "2026-08-20T18:30:00+02:00",
                    "duration_in_minutes": 90,
                    "location_id": 1,
                }
            ]
        },
    )

    title: str = Field(examples=["Match World Cup: Colombia vs Uzbekistan"])
    organizer: str = Field(
        description="Visible name of the user creating the event.",
        examples=["darwin"],
    )
    organizer_id: Optional[int] = Field(default=None, gt=0)
    duration_in_minutes: int = Field(
        gt=0,
        description="Event duration in whole minutes.",
        examples=[90],
    )
    location_id: Optional[int] = Field(default=None, gt=0)
    location: Optional[Location] = Field(default=None, exclude=True)
    scheduled_at: Optional[datetime] = Field(
        default=None,
        description=(
            "Event date and time in ISO 8601 format, including timezone. "
            "Example for Berlin summer time: "
            "2026-08-20T18:30:00+02:00. Use null when the date is undecided."
        ),
        examples=["2026-08-20T18:30:00+02:00"],
    )
    id: Optional[int] = Field(default=None, gt=0)
    status: EventStatus = EventStatus.ACTIVE
    canceled_at: Optional[datetime] = None
    deletion_scheduled_at: Optional[datetime] = None

    @field_validator("title", "organizer", mode="before")
    @classmethod
    def normalize_required_text(cls, value):
        """Trim required event text before validation."""
        if not isinstance(value, str):
            return value
        return value.strip()

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        """Require a non-empty title within the storage limit."""
        if not value:
            raise ValueError("Event title cannot be empty.")
        if len(value) > 250:
            raise ValueError("Event title cannot exceed 250 characters.")
        return value

    @field_validator("organizer")
    @classmethod
    def validate_organizer(cls, value: str) -> str:
        """Require a non-empty organizer name within the storage limit."""
        if not value:
            raise ValueError("Organizer nickname cannot be empty.")
        if len(value) > 64:
            raise ValueError("Organizer nickname cannot exceed 64 characters.")
        return value

    @field_validator(
        "scheduled_at",
        "canceled_at",
        "deletion_scheduled_at",
    )
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
    def validate_state(self) -> "Event":
        """Enforce location and lifecycle invariants."""
        if (self.location_id is None) == (self.location is None):
            raise ValueError(
                "Event must provide location_id or location, not both."
            )
        if self.status is EventStatus.ACTIVE and self.canceled_at is not None:
            raise ValueError(
                "An active event cannot have a cancellation datetime."
            )
        if self.status is EventStatus.CANCELED and self.canceled_at is None:
            raise ValueError(
                "A canceled event must have a cancellation datetime."
            )
        return self

    def schedule_deletion_after_event(
            self, delay_minutes: int, deletion_delay_when_no_date_in_minutes: int) -> "Event":
        """Return the event with deletion scheduled after its end time."""
        self._validate_delay_minutes(delay_minutes)
        deletion_scheduled_at = None
        if self.scheduled_at is not None:
            event_end = self.scheduled_at + timedelta(
                minutes=self.duration_in_minutes
            )
            deletion_scheduled_at = event_end + timedelta(minutes=delay_minutes)
        elif deletion_delay_when_no_date_in_minutes is not None:
            deletion_scheduled_at = datetime.now(timezone.utc) + timedelta(minutes=deletion_delay_when_no_date_in_minutes)
        return self.model_copy(
            update={"deletion_scheduled_at": deletion_scheduled_at}
        )

    def is_completed_at(self, current_time: datetime) -> bool:
        """Return whether the scheduled event has reached its end time."""
        if current_time.tzinfo is None:
            raise DomainValidationError(
                "Event completion datetime must include a timezone."
            )
        if self.scheduled_at is None:
            return False
        event_end = self.scheduled_at + timedelta(
            minutes=self.duration_in_minutes
        )
        return current_time.astimezone(timezone.utc) >= event_end

    def cancel(
        self,
        canceled_at: datetime,
        deletion_delay_minutes: int,
    ) -> "Event":
        """Cancel while preserving the earliest applicable deletion date."""
        if self.status is EventStatus.CANCELED:
            raise DomainValidationError("Event is already canceled.")
        if canceled_at.tzinfo is None:
            raise DomainValidationError(
                "Event cancellation datetime must include a timezone."
            )
        self._validate_delay_minutes(deletion_delay_minutes)
        normalized_canceled_at = canceled_at.astimezone(timezone.utc)
        cancellation_deletion_at = normalized_canceled_at + timedelta(
            minutes=deletion_delay_minutes
        )
        deletion_scheduled_at = cancellation_deletion_at
        if self.deletion_scheduled_at is not None:
            deletion_scheduled_at = min(
                self.deletion_scheduled_at,
                cancellation_deletion_at,
            )
        return self.model_copy(
            update={
                "status": EventStatus.CANCELED,
                "canceled_at": normalized_canceled_at,
                "deletion_scheduled_at": deletion_scheduled_at,
            }
        )

    def uncancel(self, deletion_delay_minutes: int) -> "Event":
        """Reactivate the event and restore its event-based deletion date."""
        if self.status is not EventStatus.CANCELED:
            raise DomainValidationError("Event is not canceled.")
        return self.model_copy(
            update={
                "status": EventStatus.ACTIVE,
                "canceled_at": None,
            }
        ).schedule_deletion_after_event(deletion_delay_minutes)

    @staticmethod
    def _validate_delay_minutes(value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise DomainValidationError(
                "Event deletion delay must be a non-negative integer."
            )
