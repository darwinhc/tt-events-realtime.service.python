"""Create-event use-case tests."""

from datetime import datetime

from src.domain.dtos import EventFilters
from src.domain.entities import Event
from src.domain.ports.database import EventsRepository
from src.domain.use_cases.events.create_event import create_event
from tests.unit.fakes import FakeAuthentication


class InMemoryEventsRepository(EventsRepository):
    """Small adapter proving the use case is independent from SQLite."""

    def __init__(self) -> None:
        self.created_event = None

    def create(self, event: Event) -> Event:
        self.created_event = Event(
            id=1,
            title=event.title,
            organizer=event.organizer,
            organizer_id=event.organizer_id,
            scheduled_at=event.scheduled_at,
            duration_in_minutes=event.duration_in_minutes,
            location_id=event.location_id,
            status=event.status,
            canceled_at=event.canceled_at,
            deletion_scheduled_at=event.deletion_scheduled_at,
        )
        return self.created_event

    def get_by_id(self, event_id: int):
        if self.created_event and self.created_event.id == event_id:
            return self.created_event
        return None

    def get_all(
        self,
        filters: EventFilters | None = None,
    ) -> list[Event]:
        return [self.created_event] if self.created_event else []

    def update(self, event: Event) -> Event:
        self.created_event = event
        return event

    def delete_due(self, as_of: datetime) -> int:
        return 0


def test_create_event_uses_injected_port() -> None:
    repository = InMemoryEventsRepository()

    result = create_event(
        event=Event(
            title="Portable event",
            organizer="darwin",
            scheduled_at="2026-09-10T19:00:00+02:00",
            duration_in_minutes=90,
            location_id=4,
        ),
        events=repository,
        deletion_delay_minutes=7,
        authentication=FakeAuthentication(),
    )

    assert isinstance(result, Event)
    assert result.id == 1
    assert result.scheduled_at.isoformat() == "2026-09-10T17:00:00+00:00"
    assert result.duration_in_minutes == 90
    assert result.status.value == "active"
    assert result.canceled_at is None
    assert result.deletion_scheduled_at.isoformat() == (
        "2026-09-17T18:30:00+00:00"
    )
