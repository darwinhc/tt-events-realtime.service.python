"""Join-event use case."""

from datetime import datetime, timezone
from typing import Callable

from src.domain.entities import EventStatus, Joiner, RealtimeEvent
from src.domain.ports.authentication import AuthenticationPort
from src.domain.exceptions import DomainValidationError, EntityNotFoundError
from src.domain.ports.database import EventsRepository, JoinersRepository
from src.domain.ports.events import (
    NullRealtimeEventPublisher,
    RealtimeEventPublisher,
)


def join_event(
    user_name: str,
    event_id: int,
    events: EventsRepository,
    joiners: JoinersRepository,
    authentication: AuthenticationPort,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    realtime: RealtimeEventPublisher = NullRealtimeEventPublisher(),
) -> Joiner:
    """Resolve a username and register its integer id as a participant."""
    event = events.get_by_id(event_id)
    if event is None:
        raise EntityNotFoundError(
            f"Event '{event_id}' does not exist."
        )
    if event.status is EventStatus.CANCELED:
        raise DomainValidationError("A canceled event cannot be joined.")
    current_time = clock()
    if event.is_completed_at(current_time):
        raise DomainValidationError("A completed event cannot be joined.")
    user = authentication.authenticate(user_name)
    if user.id is None:
        raise DomainValidationError("User does not have an id.")
    created_joiner = joiners.create(
        Joiner(
            user_id=user.id,
            user_name=user.name,
            event_id=event_id,
            joined_at=current_time,
        )
    )
    joiners_count = joiners.count_by_event(created_joiner.event_id)
    realtime.publish(
        RealtimeEvent(
            type="joiner.joined",
            event_id=created_joiner.event_id,
            payload={
                "joiner": created_joiner.model_dump(mode="json"),
                "joiners_count": joiners_count,
            },
        )
    )
    return created_joiner
