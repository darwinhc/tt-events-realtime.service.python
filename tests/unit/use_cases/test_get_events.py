"""Get-events enriched use-case tests."""

from datetime import date, datetime, timezone

from src.domain.dtos import EventFilters, EventQuery
from src.domain.entities import Event, EventStatus, Joiner, Location
from src.domain.ports.database import (
    EventsRepository,
    JoinersRepository,
    LocationsRepository,
)
from src.domain.use_cases.events.get_events import get_events
from src.domain.use_cases.events.get_visible_events import get_visible_events


class InMemoryEventsRepository(EventsRepository):
    def __init__(self, events: list[Event]) -> None:
        self.events = events
        self.received_filters = None

    def create(self, event: Event) -> Event:
        raise NotImplementedError

    def get_by_id(self, event_id: int):
        return next(
            (event for event in self.events if event.id == event_id),
            None,
        )

    def get_all(
        self,
        filters: EventFilters | None = None,
    ) -> list[Event]:
        self.received_filters = filters
        return self.events

    def update(self, event: Event) -> Event:
        raise NotImplementedError

    def delete_due(self, as_of: datetime) -> int:
        return 0


class InMemoryLocationsRepository(LocationsRepository):
    def __init__(self, locations: list[Location]) -> None:
        self.locations = {location.id: location for location in locations}

    def create(self, location: Location) -> Location:
        raise NotImplementedError

    def get_by_id(self, location_id: int):
        return self.locations.get(location_id)

    def get_by_ids(self, location_ids: set[int]) -> dict[int, Location]:
        return {
            location_id: self.locations[location_id]
            for location_id in location_ids
        }


class InMemoryJoinersRepository(JoinersRepository):
    def __init__(self, counts: dict[int, int]) -> None:
        self.counts = counts

    def create(self, joiner: Joiner) -> Joiner:
        raise NotImplementedError

    def get(self, user_id: str, event_id: int):
        raise NotImplementedError

    def get_all_by_event(self, event_id: int) -> list[Joiner]:
        raise NotImplementedError

    def count_by_event(self, event_id: int) -> int:
        return self.counts.get(event_id, 0)

    def count_by_events(self, event_ids: set[int]) -> dict[int, int]:
        return {
            event_id: self.counts.get(event_id, 0)
            for event_id in event_ids
        }

    def leave(self, user_id: int, event_id: int, left_at: datetime):
        raise NotImplementedError


def test_get_events_returns_location_and_joiner_count() -> None:
    location = Location(id=3, name="Main Hall", address="Berlin")
    event = Event(
        id=8,
        title="Realtime Meetup",
        organizer="darwin",
        organizer_id=1,
        scheduled_at=datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc),
        duration_in_minutes=90,
        location_id=location.id,
    )
    events = InMemoryEventsRepository([event])

    result = get_events(
        query=EventQuery(
            filters=EventFilters.from_calendar_dates(
                statuses=["active"],
                name="realtime",
                from_date=date(2026, 8, 20),
                to_date=date(2026, 8, 20),
                location_id=location.id,
            )
        ),
        events=events,
        locations=InMemoryLocationsRepository([location]),
        joiners=InMemoryJoinersRepository({event.id: 12}),
    )

    assert result.total == 1
    assert result.pages == 1
    assert result.items[0].id == event.id
    assert result.items[0].location == location
    assert result.items[0].joiners_count == 12
    assert events.received_filters.location_id == location.id
    assert events.received_filters.name == "realtime"


def test_get_events_paginates_results() -> None:
    location = Location(id=3, address="Berlin")
    events = InMemoryEventsRepository(
        [
            Event(
                id=event_id,
                title=f"Event {event_id}",
                organizer="darwin",
                organizer_id=1,
                duration_in_minutes=60,
                location_id=location.id,
            )
            for event_id in range(1, 6)
        ]
    )

    result = get_events(
        query=EventQuery(page=2, page_size=2),
        events=events,
        locations=InMemoryLocationsRepository([location]),
        joiners=InMemoryJoinersRepository({}),
    )

    assert [event.id for event in result.items] == [3, 4]
    assert result.total == 5
    assert result.page == 2
    assert result.page_size == 2
    assert result.pages == 3


def test_get_events_passes_internal_deletion_date_filters() -> None:
    location = Location(id=3, address="Berlin")
    event = Event(
        id=8,
        title="Expired event",
        organizer="darwin",
        organizer_id=1,
        duration_in_minutes=90,
        location_id=location.id,
        deletion_scheduled_at=datetime(
            2026,
            8,
            20,
            18,
            0,
            tzinfo=timezone.utc,
        ),
    )
    events = InMemoryEventsRepository([event])
    deletion_from = datetime(2026, 8, 1, tzinfo=timezone.utc)
    deletion_to = datetime(2026, 9, 1, tzinfo=timezone.utc)

    get_events(
        query=EventQuery(
            filters=EventFilters(
                deletion_scheduled_from=deletion_from,
                deletion_scheduled_until=deletion_to,
            )
        ),
        events=events,
        locations=InMemoryLocationsRepository([location]),
        joiners=InMemoryJoinersRepository({}),
    )

    assert events.received_filters.deletion_scheduled_from == deletion_from
    assert events.received_filters.deletion_scheduled_until == deletion_to


def test_get_visible_events_not_includes_active_and_canceled_before_deletion() -> None:
    location = Location(id=3, address="Berlin")
    without_deadline = Event(
        id=8,
        title="Unscheduled event",
        organizer="darwin",
        organizer_id=1,
        duration_in_minutes=90,
        location_id=location.id,
    )
    now = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)
    future_deadline = without_deadline.model_copy(
        update={
            "id": 9,
            "deletion_scheduled_at": datetime(
                2026,
                8,
                21,
                tzinfo=timezone.utc,
            ),
        }
    )
    expired_deadline = without_deadline.model_copy(
        update={
            "id": 10,
            "deletion_scheduled_at": now,
        }
    )
    canceled_visible = without_deadline.model_copy(update={"id": 11}).cancel(
        datetime(2026, 8, 20, 12, tzinfo=timezone.utc),
        deletion_delay_minutes=24*60,
    )
    canceled_expired = without_deadline.model_copy(update={"id": 12}).cancel(
        datetime(2026, 8, 19, 12, tzinfo=timezone.utc),
        deletion_delay_minutes=24*60,
    )
    events = InMemoryEventsRepository(
        [
            without_deadline,
            future_deadline,
            expired_deadline,
            canceled_visible,
            canceled_expired,
        ]
    )

    result = get_visible_events(
        events=events,
        locations=InMemoryLocationsRepository([location]),
        joiners=InMemoryJoinersRepository({}),
        clock=lambda: now,
    )

    assert [event.id for event in result] == [8, 9, 11]
    assert events.received_filters.statuses == (
        EventStatus.ACTIVE,
        EventStatus.CANCELED,
    )
    assert events.received_filters.scheduled_from is None
    assert events.received_filters.scheduled_until is None
