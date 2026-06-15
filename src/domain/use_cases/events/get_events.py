"""Get-events use case."""

from src.domain.dtos import EventDetails, EventFilters, EventPage, EventQuery
from src.domain.entities import (
    Event,
    Location,
)
from src.domain.exceptions import DomainValidationError, EntityNotFoundError
from src.domain.ports.database import (
    EventsRepository,
    JoinersRepository,
    LocationsRepository,
)


def get_events(
    query: EventQuery,
    events: EventsRepository,
    locations: LocationsRepository,
    joiners: JoinersRepository,
) -> EventPage:
    """Return filtered events enriched with location and joiner count."""
    filtered_events, total = _get_repository_page(
        events,
        query.filters,
        offset=(query.page - 1) * query.page_size,
        limit=query.page_size,
    )
    locations_by_id = locations.get_by_ids(
        _persisted_location_ids(filtered_events)
    )
    joiner_counts = joiners.count_by_events(
        _persisted_event_ids(filtered_events)
    )
    return EventPage(
        items=_build_event_details(
            filtered_events,
            locations_by_id,
            joiner_counts,
        ),
        total=total,
        page=query.page,
        page_size=query.page_size,
        pages=(total + query.page_size - 1) // query.page_size,
    )


def _get_repository_page(
    events: EventsRepository,
    filters: EventFilters,
    offset: int,
    limit: int,
) -> tuple[list[Event], int]:
    get_page = getattr(events, "get_page", None)
    if callable(get_page):
        return get_page(filters=filters, offset=offset, limit=limit)
    matching_events = events.get_all(filters)
    return matching_events[offset : offset + limit], len(matching_events)


def _persisted_location_ids(events: list[Event]) -> set[int]:
    return {
        event.location_id
        for event in events
        if event.location_id is not None
    }


def _persisted_event_ids(events: list[Event]) -> set[int]:
    return {
        event.id
        for event in events
        if event.id is not None
    }


def _build_event_details(
    events: list[Event],
    locations_by_id: dict[int, Location],
    joiner_counts: dict[int, int],
) -> list[EventDetails]:
    detailed_events = []
    for event in events:
        if event.id is None or event.location_id is None:
            raise DomainValidationError(
                "Persisted events must have event and location identifiers."
            )
        location = locations_by_id.get(event.location_id)
        if location is None:
            raise EntityNotFoundError(
                f"Location '{event.location_id}' does not exist."
            )
        detailed_events.append(
            EventDetails.from_event(
                event=event,
                location=location,
                joiners_count=joiner_counts.get(event.id, 0),
            )
        )
    return detailed_events
