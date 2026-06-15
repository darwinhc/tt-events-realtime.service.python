"""Create-event use case."""

from src.domain.entities import Event, EventStatus, RealtimeEvent
from src.domain.exceptions import DomainValidationError
from src.domain.ports.database import EventsRepository
from src.domain.ports.authentication import AuthenticationPort
from src.domain.ports.events import (
    NullRealtimeEventPublisher,
    RealtimeEventPublisher,
)


def create_event(
    event: Event,
    events: EventsRepository,
    deletion_delay_days: int,
    authentication: AuthenticationPort,
    realtime: RealtimeEventPublisher = NullRealtimeEventPublisher(),
) -> Event:
    """Create an event with an optional date-to-be-defined schedule."""
    if event.location_id is None or event.location is not None:
        raise DomainValidationError(
            "Create event requires an existing location_id."
        )
    organizer = authentication.authenticate(event.organizer)
    new_event = event.model_copy(
        update={
            "id": None,
            "organizer": organizer.name,
            "organizer_id": organizer.id,
            "status": EventStatus.ACTIVE,
            "canceled_at": None,
            "deletion_scheduled_at": None,
        }
    )
    event_with_deletion_policy = new_event.schedule_deletion_after_event(
        deletion_delay_days
    )
    created_event = events.create(event_with_deletion_policy)
    realtime.publish(
        RealtimeEvent(
            type="event.created",
            event_id=created_event.id,
            payload=created_event.model_dump(mode="json"),
        )
    )
    return created_event
