"""Cancel-event use case."""

from datetime import datetime, timezone
from typing import Callable

from src.domain.exceptions import AuthorizationError, EntityNotFoundError
from src.domain.entities import Event, RealtimeEvent
from src.domain.ports.authentication import AuthenticationPort
from src.domain.ports.database import EventsRepository
from src.domain.ports.events import (
    NullRealtimeEventPublisher,
    RealtimeEventPublisher,
)


def cancel_event(
    event_id: int,
    actor_user_name: str,
    events: EventsRepository,
    deletion_delay_minutes: int,
    authentication: AuthenticationPort,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    realtime: RealtimeEventPublisher = NullRealtimeEventPublisher(),
) -> Event:
    """Cancel an event using the earliest applicable deletion schedule."""
    event = events.get_by_id(event_id)
    if event is None:
        raise EntityNotFoundError(f"Event '{event_id}' does not exist.")
    actor = authentication.authenticate(actor_user_name)
    if actor.id != event.organizer_id:
        raise AuthorizationError(
            "Only the event organizer can cancel this event."
        )
    canceled_event = event.cancel(
        canceled_at=clock(),
        deletion_delay_minutes=deletion_delay_minutes,
    )
    updated_event = events.update(canceled_event)
    realtime.publish(
        RealtimeEvent(
            type="event.canceled",
            event_id=updated_event.id,
            payload=updated_event.model_dump(mode="json"),
        )
    )
    return updated_event
