"""Uncancel-event use case."""

from src.domain.entities import Event, RealtimeEvent
from src.domain.exceptions import AuthorizationError, EntityNotFoundError
from src.domain.ports.authentication import AuthenticationPort
from src.domain.ports.database import EventsRepository
from src.domain.ports.events import (
    NullRealtimeEventPublisher,
    RealtimeEventPublisher,
)


def uncancel_event(
    event_id: int,
    actor_user_name: str,
    events: EventsRepository,
    deletion_delay_days: int,
    authentication: AuthenticationPort,
    realtime: RealtimeEventPublisher = NullRealtimeEventPublisher(),
) -> Event:
    """Reactivate an event when requested by its organizer."""
    event = events.get_by_id(event_id)
    if event is None:
        raise EntityNotFoundError(f"Event '{event_id}' does not exist.")
    actor = authentication.authenticate(actor_user_name)
    if actor.id != event.organizer_id:
        raise AuthorizationError(
            "Only the event organizer can uncancel this event."
        )
    updated_event = events.update(
        event.uncancel(deletion_delay_days=deletion_delay_days)
    )
    realtime.publish(
        RealtimeEvent(
            type="event.uncanceled",
            event_id=updated_event.id,
            payload=updated_event.model_dump(mode="json"),
        )
    )
    return updated_event
