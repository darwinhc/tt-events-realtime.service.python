"""Verify event dates."""
from datetime import datetime, timedelta

from src.domain.entities import Event
from src.domain.exceptions import DomainValidationError


def verify_event_dates_consistency(event: Event, now: datetime) -> None:
    """Verify that the event has a valid date range relative to ``now``."""
    if event.deletion_scheduled_at is None:
        raise DomainValidationError("Event must have a deletion date.")

    if (
        event.scheduled_at is not None
        and event.scheduled_at + timedelta(minutes=event.duration_in_minutes) < now
    ):
        raise DomainValidationError("Event must have a scheduled date in the future.")

    if event.deletion_scheduled_at < now:
        raise DomainValidationError("Event must have a deletion date in the future.")
