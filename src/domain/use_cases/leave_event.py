"""Leave-event use case."""

from datetime import datetime, timezone
from typing import Callable

from src.domain.entities import Joiner, RealtimeEvent
from src.domain.exceptions import EntityNotFoundError
from src.domain.ports.database import JoinersRepository
from src.domain.ports.authentication import AuthenticationPort
from src.domain.ports.events import (
    NullRealtimeEventPublisher,
    RealtimeEventPublisher,
)


def leave_event(
    user_name: str,
    event_id: int,
    joiners: JoinersRepository,
    authentication: AuthenticationPort,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    realtime: RealtimeEventPublisher = NullRealtimeEventPublisher(),
) -> Joiner:
    """Resolve a user and mark its active participation as left."""
    user = authentication.authenticate(user_name)
    left_joiner = joiners.leave(
        user_id=user.id,
        event_id=event_id,
        left_at=clock(),
    )
    if left_joiner is None:
        raise EntityNotFoundError(
            f"User '{user.name}' is not joined to event '{event_id}'."
        )
    joiners_count = joiners.count_by_event(left_joiner.event_id)
    realtime.publish(
        RealtimeEvent(
            type="joiner.left",
            event_id=left_joiner.event_id,
            payload={
                "joiner": left_joiner.model_dump(mode="json"),
                "joiners_count": joiners_count,
            },
        )
    )
    return left_joiner
