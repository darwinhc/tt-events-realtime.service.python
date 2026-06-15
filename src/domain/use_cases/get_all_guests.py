"""Get-all-guests use case."""

from src.domain.entities import Joiner
from src.domain.exceptions import EntityNotFoundError
from src.domain.ports.database import EventsRepository, JoinersRepository


def get_all_guests(
    event_id: int,
    events: EventsRepository,
    joiners: JoinersRepository,
) -> list[Joiner]:
    """Return all guests participating in an event."""
    if events.get_by_id(event_id) is None:
        raise EntityNotFoundError(f"Event '{event_id}' does not exist.")
    return joiners.get_all_by_event(event_id)
