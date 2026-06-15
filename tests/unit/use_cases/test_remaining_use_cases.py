"""Edge cases for the remaining application use cases."""

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from src.domain.dtos import EventFilters, EventQuery
from src.domain.entities import Event, Joiner, Location
from src.domain.exceptions import (
    DomainValidationError,
    EntityNotFoundError,
)
from src.domain.use_cases.events.cancel_event import cancel_event
from src.domain.use_cases.events.create_event import create_event
from src.domain.use_cases.events.delete_expired_events import (
    delete_expired_events,
)
from src.domain.use_cases.events.get_event import get_event
from src.domain.use_cases.events.get_events import get_events
from src.domain.use_cases.get_all_guests import get_all_guests
from src.domain.use_cases.join_event import join_event
from tests.unit.fakes import FakeAuthentication


class Events:
    def __init__(self, event=None, all_events=None) -> None:
        self.event = event
        self.all_events = all_events if all_events is not None else []
        self.deleted_at = None
        self.fail_create = False

    def get_by_id(self, event_id):
        return self.event if self.event and self.event.id == event_id else None

    def get_all(self, filters=None):
        return self.all_events

    def create(self, event):
        if self.fail_create:
            raise RuntimeError("database unavailable")
        self.event = event.model_copy(update={"id": 99})
        return self.event

    def update(self, event):
        self.event = event
        return event

    def delete_due(self, as_of):
        self.deleted_at = as_of
        return 3


class Locations:
    def __init__(self, locations=()) -> None:
        self.locations = {location.id: location for location in locations}

    def get_by_id(self, location_id):
        return self.locations.get(location_id)

    def get_by_ids(self, location_ids):
        return {
            location_id: self.locations[location_id]
            for location_id in location_ids
            if location_id in self.locations
        }


class Joiners:
    def __init__(self, joiners=()) -> None:
        self.joiners = list(joiners)

    def create(self, joiner):
        self.joiners.append(joiner)
        return joiner

    def count_by_event(self, event_id):
        return sum(
            j.event_id == event_id and j.left_at is None
            for j in self.joiners
        )

    def count_by_events(self, event_ids):
        return {
            event_id: self.count_by_event(event_id)
            for event_id in event_ids
        }

    def get_all_by_event(self, event_id):
        return [
            j
            for j in self.joiners
            if j.event_id == event_id and j.left_at is None
        ]

    def leave(self, user_id, event_id, left_at):
        for index, joiner in enumerate(self.joiners):
            if (
                joiner.user_id == user_id
                and joiner.event_id == event_id
                and joiner.left_at is None
            ):
                left = joiner.model_copy(update={"left_at": left_at})
                self.joiners[index] = left
                return left
        return None


class Publisher:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event):
        self.events.append(event)


def _event(event_id=1, location_id=10) -> Event:
    return Event(
        id=event_id,
        title="Event",
        organizer="darwin",
        organizer_id=1,
        duration_in_minutes=60,
        location_id=location_id,
    )


def test_get_event_returns_authoritative_details() -> None:
    event = _event()
    location = Location(id=10, address="Berlin")
    joiners = Joiners(
        [
            Joiner(user_id=2, user_name="alice", event_id=1),
            Joiner(user_id=3, user_name="bob", event_id=1),
        ]
    )

    result = get_event(
        event_id=1,
        events=Events(event),
        locations=Locations([location]),
        joiners=joiners,
    )

    assert result.id == 1
    assert result.location == location
    assert result.joiners_count == 2


def test_get_event_rejects_missing_event_or_location() -> None:
    with pytest.raises(EntityNotFoundError, match="Event"):
        get_event(1, Events(), Locations(), Joiners())
    with pytest.raises(EntityNotFoundError, match="Location"):
        get_event(1, Events(_event()), Locations(), Joiners())


def test_get_events_rejects_invalid_filters_and_corrupt_persisted_data() -> None:
    with pytest.raises(DomainValidationError, match="from_date"):
        get_events(
            EventQuery(
                filters=EventFilters.from_calendar_dates(
                    from_date=date(2026, 8, 21),
                    to_date=date(2026, 8, 20),
                )
            ),
            Events(),
            Locations(),
            Joiners(),
        )
    with pytest.raises(ValidationError):
        EventFilters(statuses=("unknown",))

    event_without_id = _event().model_copy(update={"id": None})
    with pytest.raises(DomainValidationError, match="identifiers"):
        get_events(
            EventQuery(),
            Events(all_events=[event_without_id]),
            Locations(),
            Joiners(),
        )

    with pytest.raises(EntityNotFoundError, match="Location"):
        get_events(
            EventQuery(),
            Events(all_events=[_event()]),
            Locations(),
            Joiners(),
        )


def test_guest_query_requires_an_existing_event() -> None:
    with pytest.raises(EntityNotFoundError):
        get_all_guests(1, Events(), Joiners())


def test_delete_expired_events_uses_the_injected_clock() -> None:
    cutoff = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
    events = Events()

    result = delete_expired_events(events, clock=lambda: cutoff)

    assert result == 3
    assert events.deleted_at == cutoff


def test_mutations_publish_only_after_successful_persistence() -> None:
    publisher = Publisher()
    events = Events()
    events.fail_create = True

    with pytest.raises(RuntimeError):
        create_event(
            Event(
                title="Event",
                organizer="darwin",
                duration_in_minutes=60,
                location_id=10,
            ),
            events=events,
            deletion_delay_minutes=7,
            authentication=FakeAuthentication(),
            realtime=publisher,
        )

    assert publisher.events == []


def test_create_cancel_and_join_publish_expected_notifications() -> None:
    publisher = Publisher()
    events = Events()
    created = create_event(
        Event(
            title="Event",
            organizer="darwin",
            duration_in_minutes=60,
            location_id=10,
        ),
        events=events,
        deletion_delay_minutes=7,
        authentication=FakeAuthentication(),
        realtime=publisher,
    )
    canceled = cancel_event(
        created.id,
        actor_user_name="darwin",
        events=events,
        deletion_delay_minutes=1,
        authentication=FakeAuthentication(),
        clock=lambda: datetime(2026, 8, 20, tzinfo=timezone.utc),
        realtime=publisher,
    )

    assert canceled.status.value == "canceled"
    assert [event.type for event in publisher.events] == [
        "event.created",
        "event.canceled",
    ]

    active = _event()
    join_publisher = Publisher()
    join_event(
        "guest",
        1,
        events=Events(active),
        joiners=Joiners(),
        authentication=FakeAuthentication({"guest": 2}),
        realtime=join_publisher,
    )
    assert join_publisher.events[0].payload["joiners_count"] == 1


def test_mutations_reject_missing_entities_and_invalid_create_shape() -> None:
    with pytest.raises(EntityNotFoundError):
        cancel_event(
            1,
            "darwin",
            Events(),
            deletion_delay_minutes=1,
            authentication=FakeAuthentication(),
        )
    with pytest.raises(EntityNotFoundError):
        join_event(
            "guest",
            1,
            events=Events(),
            joiners=Joiners(),
            authentication=FakeAuthentication({"guest": 2}),
        )

    embedded = Event(
        title="Embedded",
        organizer="darwin",
        duration_in_minutes=60,
        location=Location(address="Remote"),
    )
    with pytest.raises(DomainValidationError, match="location_id"):
        create_event(
            embedded,
            Events(),
            deletion_delay_minutes=7,
            authentication=FakeAuthentication(),
        )
