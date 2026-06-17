"""Uncancel-event use-case tests."""

from datetime import datetime, timezone

import pytest

from src.domain.dtos import EventFilters
from src.domain.entities import Event
from src.domain.exceptions import (
    AuthorizationError,
    DomainValidationError,
    EntityNotFoundError,
)
from src.domain.ports.database import EventsRepository
from src.domain.use_cases.events.uncancel_event import uncancel_event
from tests.unit.fakes import FakeAuthentication


class Events(EventsRepository):
    def __init__(self, event: Event | None) -> None:
        self.event = event
        self.update_calls = 0

    def create(self, event: Event) -> Event:
        self.event = event
        return event

    def get_by_id(self, event_id: int):
        if self.event is None or self.event.id != event_id:
            return None
        return self.event

    def get_all(
        self,
        filters: EventFilters | None = None,
    ) -> list[Event]:
        return [self.event] if self.event is not None else []

    def update(self, event: Event) -> Event:
        self.update_calls += 1
        self.event = event
        return event

    def delete_due(self, as_of: datetime) -> int:
        return 0


class Publisher:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event) -> None:
        self.events.append(event)


def _canceled_event() -> Event:
    return Event(
        id=8,
        title="Canceled event",
        organizer="darwin",
        organizer_id=1,
        scheduled_at=datetime(2026, 8, 20, 18, tzinfo=timezone.utc),
        duration_in_minutes=60,
        location_id=1,
    ).schedule_deletion_after_event(7, 20).cancel(
        datetime(2026, 8, 10, 12, tzinfo=timezone.utc),
        deletion_delay_minutes=1,
    )


def test_organizer_can_uncancel_event() -> None:
    events = Events(_canceled_event())
    publisher = Publisher()

    result = uncancel_event(
        event_id=8,
        actor_user_name="darwin",
        events=events,
        deletion_delay_minutes=7*60*24,
        authentication=FakeAuthentication(),
        realtime=publisher,
        deletion_delay_when_no_date_in_minutes=4
    )

    assert result.status.value == "active"
    assert result.canceled_at is None
    assert result.deletion_scheduled_at == datetime(
        2026,
        8,
        27,
        19,
        tzinfo=timezone.utc,
    )
    assert publisher.events[0].type == "event.uncanceled"
    assert publisher.events[0].payload["status"] == "active"


def test_non_organizer_cannot_uncancel_event() -> None:
    events = Events(_canceled_event())

    with pytest.raises(AuthorizationError, match="organizer"):
        uncancel_event(
            event_id=8,
            actor_user_name="another-user",
            events=events,
            deletion_delay_minutes=7*60*24,
            authentication=FakeAuthentication(
                {"darwin": 1, "another-user": 2}
            ),
            deletion_delay_when_no_date_in_minutes=4
        )

    assert events.update_calls == 0


def test_uncancel_rejects_missing_or_active_event() -> None:
    with pytest.raises(EntityNotFoundError):
        uncancel_event(
            event_id=8,
            actor_user_name="darwin",
            events=Events(None),
            deletion_delay_minutes=7*60*24,
            authentication=FakeAuthentication(),
            deletion_delay_when_no_date_in_minutes=4
        )

    active = _canceled_event().uncancel(deletion_delay_minutes=7,
                                        deletion_delay_when_no_date_in_minutes=4)
    with pytest.raises(DomainValidationError, match="not canceled"):
        uncancel_event(
            event_id=8,
            actor_user_name="darwin",
            events=Events(active),
            deletion_delay_minutes=7*60*24,
            authentication=FakeAuthentication(),
            deletion_delay_when_no_date_in_minutes=2
        )
