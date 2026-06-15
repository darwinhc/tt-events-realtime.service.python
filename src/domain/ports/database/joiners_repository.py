"""Joiner repository port."""

from abc import abstractmethod
from datetime import datetime
from typing import Optional

from src.domain.entities import Joiner

from .repository import Repository


class JoinersRepository(Repository):
    """Technology-neutral persistence operations for event joiners."""

    @abstractmethod
    def create(self, joiner: Joiner) -> Joiner:
        """Persist an event joiner."""
        raise NotImplementedError

    @abstractmethod
    def get(self, user_id: int, event_id: int) -> Optional[Joiner]:
        """Return the active joiner for a user and event."""
        raise NotImplementedError

    @abstractmethod
    def get_all_by_event(self, event_id: int) -> list[Joiner]:
        """Return all active joiners for an event."""
        raise NotImplementedError

    @abstractmethod
    def count_by_event(self, event_id: int) -> int:
        """Return the number of joiners for an event."""
        raise NotImplementedError

    @abstractmethod
    def count_by_events(self, event_ids: set[int]) -> dict[int, int]:
        """Return joiner counts indexed by event id."""
        raise NotImplementedError

    @abstractmethod
    def leave(
        self,
        user_id: int,
        event_id: int,
        left_at: datetime,
    ) -> Optional[Joiner]:
        """Mark and return the active joiner as having left."""
        raise NotImplementedError
