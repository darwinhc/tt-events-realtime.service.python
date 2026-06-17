"""Create-event use case."""

from src.domain.use_cases.events.verify_event_dates import verify_event_dates_consistency
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
    deletion_delay_minutes: int,
    authentication: AuthenticationPort,
    deletion_delay_when_no_date_in_minutes: int = 7*24*60,
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
    _event = new_event.schedule_deletion_after_event(
        delay_minutes=deletion_delay_minutes,
        deletion_delay_when_no_date_in_minutes=deletion_delay_when_no_date_in_minutes
    )

    verify_event_dates_consistency(_event)
    created_event = events.create(_event)
    realtime.publish(
        RealtimeEvent(
            type="event.created",
            event_id=created_event.id,
            payload=created_event.model_dump(mode="json"),
        )
    )
    return created_event
