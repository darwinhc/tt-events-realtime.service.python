"""Delete-expired-events use case."""

from datetime import datetime, timezone
from typing import Callable

from src.domain.ports.database import EventsRepository


def delete_expired_events(
    events: EventsRepository,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> int:
    """Permanently delete events whose scheduled deletion time has arrived."""
    return events.delete_due(clock())
