"""Get non-expired events whose deletion deadline hasn't passed."""

from datetime import datetime, timezone
from typing import Callable

from src.domain.dtos import EventPage, EventQuery
from src.domain.ports.database import (
    EventsRepository,
    JoinersRepository,
    LocationsRepository,
)

from .get_events import get_events


def get_non_expired_events(
    events: EventsRepository,
    locations: LocationsRepository,
    joiners: JoinersRepository,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    query: EventQuery = EventQuery(page_size=100),
) -> EventPage:
    """Return active events whose deletion deadline is before now."""
    filters = query.filters
    effective_deletion_from = filters.deletion_scheduled_from
    if (
        filters.deletion_scheduled_from is None
        and filters.deletion_scheduled_until is None
    ):
        effective_deletion_from = clock()
    return get_events(
        query=query.model_copy(
            update={
                "filters": filters.model_copy(
                    update={
                        "deletion_scheduled_from": effective_deletion_from,
                    }
                )
            }
        ),
        events=events,
        locations=locations,
        joiners=joiners,
    )
