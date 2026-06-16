"""Event query filters."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Sequence, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..entities import EventStatus
from ..exceptions import DomainValidationError


class EventFilters(BaseModel):
    """Technology-neutral filters for listing events."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    statuses: Tuple[EventStatus, ...] = ()
    name: Optional[str] = None
    scheduled_from: Optional[datetime] = None
    scheduled_until: Optional[datetime] = None
    deletion_scheduled_from: Optional[datetime] = None
    deletion_scheduled_until: Optional[datetime] = None
    location_id: Optional[int] = Field(default=None, gt=0)

    @classmethod
    def from_calendar_dates(
        cls,
        *,
        statuses: Optional[Sequence[Union[EventStatus, str]]] = None,
        name: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        location_id: Optional[int] = None,
        deletion_date_from: Optional[datetime] = None,
        deletion_date_to: Optional[datetime] = None,
    ) -> "EventFilters":
        """Build repository boundaries from inclusive calendar dates."""
        if from_date is not None and to_date is not None and from_date > to_date:
            raise DomainValidationError(
                "Event from_date cannot be after to_date."
            )
        scheduled_from = (
            datetime.combine(from_date, time.min, tzinfo=timezone.utc)
            if from_date is not None
            else None
        )
        scheduled_until = (
            datetime.combine(
                to_date + timedelta(minutes=1),
                time.min,
                tzinfo=timezone.utc,
            )
            if to_date is not None
            else None
        )
        return cls(
            statuses=tuple(statuses or ()),
            name=name,
            scheduled_from=scheduled_from,
            scheduled_until=scheduled_until,
            deletion_scheduled_from=deletion_date_from,
            deletion_scheduled_until=deletion_date_to,
            location_id=location_id,
        )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value):
        """Trim and reject an empty event-name filter."""
        if value is None:
            return None
        normalized_value = str(value).strip()
        if not normalized_value:
            raise ValueError("Event name filter cannot be empty.")
        return normalized_value

    @field_validator(
        "scheduled_from",
        "scheduled_until",
        "deletion_scheduled_from",
        "deletion_scheduled_until",
    )
    @classmethod
    def validate_datetime(
        cls,
        value: Optional[datetime],
    ) -> Optional[datetime]:
        """Require timezone-aware temporal filter boundaries."""
        if value is not None and value.tzinfo is None:
            raise ValueError("Event date filters must include a timezone.")
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> "EventFilters":
        """Require each supplied range to have increasing boundaries."""
        ranges = (
            (
                self.scheduled_from,
                self.scheduled_until,
                "Event start date filter",
            ),
            (
                self.deletion_scheduled_from,
                self.deletion_scheduled_until,
                "Event deletion date filter",
            ),
        )
        for range_start, range_end, field_label in ranges:
            if (
                range_start is not None
                and range_end is not None
                and range_start >= range_end
            ):
                raise ValueError(f"{field_label} must start before it ends.")
        return self
