"""Get visible events for the operational API."""

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


def get_visible_events(
    events: EventsRepository,
    locations: LocationsRepository,
    joiners: JoinersRepository,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> list[EventDetails]:
    """Return events whose deletion deadline has not expired."""
    current_time = clock().astimezone(timezone.utc)
    candidate_events = []
    page_number = 1
    while True:
        result_page = get_events(
            query=EventQuery(
                filters=EventFilters(
                    statuses=(EventStatus.ACTIVE, EventStatus.CANCELED),
                ),
                page=page_number,
                page_size=100,
            ),
            events=events,
            locations=locations,
            joiners=joiners,
        )
        candidate_events.extend(result_page.items)
        if page_number >= result_page.pages:
            break
        page_number += 1
    return [
        event
        for event in candidate_events
        if event.status in (EventStatus.ACTIVE, EventStatus.CANCELED)
        and (
            event.deletion_scheduled_at is None
            or event.deletion_scheduled_at > current_time
        )
    ]
