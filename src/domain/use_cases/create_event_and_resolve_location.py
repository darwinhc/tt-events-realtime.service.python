"""Create-event-and-resolve-location use case."""

from src.domain.entities import Event
from src.domain.exceptions import DomainValidationError, EntityNotFoundError
from src.domain.ports.database import EventsRepository, LocationsRepository
from src.domain.ports.authentication import AuthenticationPort
from src.domain.ports.events import (
    NullRealtimeEventPublisher,
    RealtimeEventPublisher,
)

from .events import create_event
from .locations import create_location


def create_event_and_resolve_location(
    event: Event,
    events: EventsRepository,
    locations: LocationsRepository,
    deletion_delay_days: int,
    authentication: AuthenticationPort,
    realtime: RealtimeEventPublisher = NullRealtimeEventPublisher(),
) -> Event:
    """Create an event using an existing or newly created location."""
    if event.location_id is not None:
        if locations.get_by_id(event.location_id) is None:
            raise EntityNotFoundError(
                f"Location '{event.location_id}' does not exist."
            )
        resolved_event = event
    elif event.location is not None:
        created_location = create_location(
            location=event.location,
            locations=locations,
        )
        resolved_event = Event.model_validate(
            {
                **event.model_dump(exclude={"location"}),
                "location_id": created_location.id,
            }
        )
    else:
        raise DomainValidationError("Event has no location information.")

    return create_event(
        event=resolved_event,
        events=events,
        deletion_delay_minutes=deletion_delay_days,
        authentication=authentication,
        realtime=realtime,
    )
