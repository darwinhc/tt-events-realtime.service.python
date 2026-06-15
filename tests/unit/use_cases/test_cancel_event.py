"""Cancel-event use-case tests."""

from datetime import datetime, timezone

from src.domain.dtos import EventFilters
from src.domain.entities import Event
from src.domain.ports.database import EventsRepository
from src.domain.use_cases.events.cancel_event import cancel_event
from tests.unit.fakes import FakeAuthentication


class InMemoryEventsRepository(EventsRepository):
    def __init__(self, event: Event) -> None:
        self.event = event

    def create(self, event: Event) -> Event:
        self.event = event
        return event

    def get_by_id(self, event_id: int):
        return self.event if self.event.id == event_id else None

    def get_all(
        self,
        filters: EventFilters | None = None,
    ) -> list[Event]:
        return [self.event]

    def update(self, event: Event) -> Event:
        self.event = event
        return event

    def delete_due(self, as_of: datetime) -> int:
        return 0


def test_cancel_event_uses_configured_deletion_delay() -> None:
    repository = InMemoryEventsRepository(
        Event(
            id=8,
            title="Cancelable event",
            organizer="darwin",
            organizer_id=1,
            duration_in_minutes=120,
            location_id=1,
        )
    )
    canceled_at = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)

    result = cancel_event(
        event_id=8,
        actor_user_name="darwin",
        events=repository,
        deletion_delay_minutes=1,
        authentication=FakeAuthentication(),
        clock=lambda: canceled_at,
    )

    assert isinstance(result, Event)
    assert result.status.value == "canceled"
    assert result.canceled_at.isoformat() == "2026-07-01T10:00:00+00:00"
    assert result.deletion_scheduled_at.isoformat() == (
        "2026-07-02T10:00:00+00:00"
    )


def test_cancel_event_preserves_earlier_existing_deletion_date() -> None:
    existing_deletion_at = datetime(
        2026,
        7,
        1,
        8,
        0,
        tzinfo=timezone.utc,
    )
    repository = InMemoryEventsRepository(
        Event(
            id=8,
            title="Past event",
            organizer="darwin",
            organizer_id=1,
            duration_in_minutes=120,
            location_id=1,
            deletion_scheduled_at=existing_deletion_at,
        )
    )

    result = cancel_event(
        event_id=8,
        actor_user_name="darwin",
        events=repository,
        deletion_delay_minutes=1,
        authentication=FakeAuthentication(),
        clock=lambda: datetime(
            2026,
            7,
            1,
            10,
            0,
            tzinfo=timezone.utc,
        ),
    )

    assert result.deletion_scheduled_at == existing_deletion_at
