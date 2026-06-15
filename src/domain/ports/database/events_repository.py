"""Event repository port."""

from abc import abstractmethod
from datetime import datetime
from typing import Optional

from src.domain.dtos import EventFilters
from src.domain.entities import Event

from .repository import Repository


class EventsRepository(Repository):
    """Technology-neutral persistence operations for events."""

    @abstractmethod
    def create(self, event: Event) -> Event:
        """Persist and return an event with its generated id."""
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, event_id: int) -> Optional[Event]:
        """Return an event by id, if present."""
        raise NotImplementedError

    @abstractmethod
    def get_all(
        self,
        filters: Optional[EventFilters] = None,
    ) -> list[Event]:
        """Return events matching all provided filters."""
        raise NotImplementedError

    def get_page(
        self,
        filters: Optional[EventFilters],
        offset: int,
        limit: int,
    ) -> tuple[list[Event], int]:
        """Return one filtered page and the total matching row count."""
        matching_events = self.get_all(filters)
        return matching_events[offset : offset + limit], len(matching_events)

    @abstractmethod
    def update(self, event: Event) -> Event:
        """Persist and return an existing event."""
        raise NotImplementedError

    @abstractmethod
    def delete_due(self, as_of: datetime) -> int:
        """Delete events whose scheduled deletion time has arrived."""
        raise NotImplementedError
