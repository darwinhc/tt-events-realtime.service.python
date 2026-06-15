"""Authorized event-update use-case tests."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.domain.dtos import EventUpdate
from src.domain.entities import Event, Location
from src.domain.exceptions import (
    AuthorizationError,
    DomainValidationError,
    EntityNotFoundError,
)
from src.domain.use_cases.events.update_event import update_event
from tests.unit.fakes import FakeAuthentication


class Events:
    def __init__(self, event=None) -> None:
        self.event = event
        self.update_calls = 0

    def get_by_id(self, event_id):
        return self.event if self.event and self.event.id == event_id else None

    def update(self, event):
        self.update_calls += 1
        self.event = event
        return event


class Locations:
    def __init__(self, *location_ids) -> None:
        self.location_ids = set(location_ids)

    def get_by_id(self, location_id):
        if location_id not in self.location_ids:
            return None
        return Location(id=location_id, address="Known location")


class Publisher:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event):
        self.events.append(event)


def _event() -> Event:
    return Event(
        id=1,
        title="Original title",
        organizer="darwin",
        organizer_id=1,
        scheduled_at=datetime(2026, 8, 20, 18, tzinfo=timezone.utc),
        duration_in_minutes=60,
        location_id=10,
    )


def test_organizer_updates_editable_fields_and_recalculates_deletion() -> None:
    events = Events(_event())
    publisher = Publisher()

    result = update_event(
        event_id=1,
        actor_user_name="darwin",
        changes=EventUpdate(
            title="Updated title",
            scheduled_at="2026-09-01T20:00:00+02:00",
            duration_in_minutes=90,
            location_id=20,
        ),
        events=events,
        locations=Locations(20),
        deletion_delay_days=7,
        authentication=FakeAuthentication(),
        realtime=publisher,
    )

    assert result.title == "Updated title"
    assert result.organizer == "darwin"
    assert result.scheduled_at == datetime(
        2026, 9, 1, 18, tzinfo=timezone.utc
    )
    assert result.duration_in_minutes == 90
    assert result.location_id == 20
    assert result.deletion_scheduled_at == datetime(
        2026, 9, 8, 19, 30, tzinfo=timezone.utc
    )
    assert publisher.events[0].type == "event.updated"
    assert publisher.events[0].payload["title"] == "Updated title"


def test_organizer_can_clear_schedule_and_deletion_date() -> None:
    result = update_event(
        event_id=1,
        actor_user_name="darwin",
        changes=EventUpdate(scheduled_at=None),
        events=Events(_event()),
        locations=Locations(),
        deletion_delay_days=7,
        authentication=FakeAuthentication(),
    )

    assert result.scheduled_at is None
    assert result.deletion_scheduled_at is None


def test_non_organizer_cannot_update_or_publish() -> None:
    events = Events(_event())
    publisher = Publisher()

    with pytest.raises(AuthorizationError):
        update_event(
            event_id=1,
            actor_user_name="another-user",
            changes=EventUpdate(title="Forbidden"),
            events=events,
            locations=Locations(),
            deletion_delay_days=7,
            authentication=FakeAuthentication(
                {"darwin": 1, "another-user": 2}
            ),
            realtime=publisher,
        )

    assert events.update_calls == 0
    assert publisher.events == []


def test_update_rejects_missing_canceled_event_and_unknown_location() -> None:
    with pytest.raises(EntityNotFoundError, match="Event"):
        update_event(
            1,
            "darwin",
            EventUpdate(title="Missing"),
            Events(),
            Locations(),
            7,
            FakeAuthentication(),
        )

    canceled = _event().cancel(
        datetime(2026, 8, 10, tzinfo=timezone.utc),
        deletion_delay_minutes=1,
    )
    with pytest.raises(DomainValidationError, match="canceled"):
        update_event(
            1,
            "darwin",
            EventUpdate(title="Too late"),
            Events(canceled),
            Locations(),
            7,
            FakeAuthentication(),
        )

    with pytest.raises(EntityNotFoundError, match="Location"):
        update_event(
            1,
            "darwin",
            EventUpdate(location_id=999),
            Events(_event()),
            Locations(),
            7,
            FakeAuthentication(),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": None},
        {"duration_in_minutes": None},
        {"location_id": None},
        {"organizer": "hacker"},
        {"status": "canceled"},
    ],
)
def test_update_payload_rejects_empty_null_and_immutable_fields(payload) -> None:
    with pytest.raises(ValidationError):
        EventUpdate.model_validate(payload)
