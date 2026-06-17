"""Get joiners for events use-case."""
from src.domain.dtos.joiner_info import JoinerInfo
from src.domain.ports.database import JoinersRepository


def get_joiners_for_events(
    event_ids: set[int],
    joiners: JoinersRepository,
) -> list[JoinerInfo]:
    """Return all joiners for the given events."""
    if not event_ids:
        return []
    return joiners.get_joiners_for_events(event_ids)
