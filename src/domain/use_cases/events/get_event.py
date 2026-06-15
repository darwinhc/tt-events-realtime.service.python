"""Get-event use case."""

from src.domain.dtos import EventDetails
from src.domain.exceptions import EntityNotFoundError
from src.domain.ports.database import (
    EventsRepository,
    JoinersRepository,
    LocationsRepository,
)


def get_event(
    event_id: int,
    events: EventsRepository,
    locations: LocationsRepository,
    joiners: JoinersRepository,
) -> EventDetails:
    """Return one event with its current location and participation count."""
    event = events.get_by_id(event_id)
    if event is None:
        raise EntityNotFoundError(f"Event '{event_id}' does not exist.")
    location = locations.get_by_id(event.location_id)
    if location is None:
        raise EntityNotFoundError(
            f"Location '{event.location_id}' does not exist."
        )
    return EventDetails.from_event(
        event=event,
        location=location,
        joiners_count=joiners.count_by_event(event_id),
    )
