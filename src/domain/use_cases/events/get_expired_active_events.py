"""Get active events whose deletion deadline has passed."""

from datetime import datetime, timezone
from typing import Callable

from src.domain.dtos import EventDetails, EventFilters, EventQuery
from src.domain.entities import EventStatus
from src.domain.ports.database import (
    EventsRepository,
    JoinersRepository,
    LocationsRepository,
)

from .get_events import get_events


def get_expired_active_events(
    events: EventsRepository,
    locations: LocationsRepository,
    joiners: JoinersRepository,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> list[EventDetails]:
    """Return active events whose deletion deadline is before now."""
    expired_events = []
    page_number = 1
    while True:
        result_page = get_events(
            query=EventQuery(
                filters=EventFilters(
                    statuses=(EventStatus.ACTIVE,),
                    deletion_scheduled_until=clock(),
                ),
                page=page_number,
                page_size=100,
            ),
            events=events,
            locations=locations,
            joiners=joiners,
        )
        expired_events.extend(result_page.items)
        if page_number >= result_page.pages:
            return expired_events
        page_number += 1
