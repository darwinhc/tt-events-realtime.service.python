"""Create-event-and-resolve-location use-case tests."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.domain.dtos import EventFilters
from src.domain.entities import Event, Location
from src.domain.ports.database import EventsRepository, LocationsRepository
from src.domain.use_cases.create_event_and_resolve_location import (
    create_event_and_resolve_location,
)
from tests.unit.fakes import FakeAuthentication


class InMemoryEventsRepository(EventsRepository):
    def __init__(self) -> None:
        self.event = None

    def create(self, event: Event) -> Event:
        self.event = Event(
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
        return self.event

    def get_by_id(self, event_id: int):
        return self.event if self.event and self.event.id == event_id else None

    def get_all(
        self,
        filters: EventFilters | None = None,
    ) -> list[Event]:
        return [self.event] if self.event else []

    def update(self, event: Event) -> Event:
        self.event = event
        return event

    def delete_due(self, as_of: datetime) -> int:
        return 0


class InMemoryLocationsRepository(LocationsRepository):
    def __init__(self) -> None:
        self.locations = {4: Location(id=4, name="Existing Hall")}

    def create(self, location: Location) -> Location:
        created = Location(
            id=5,
            name=location.name,
            address=location.address,
            country=location.country,
            city=location.city,
            postal_code=location.postal_code,
            coordinates=location.coordinates,
        )
        self.locations[created.id] = created
        return created

    def get_by_id(self, location_id: int):
        return self.locations.get(location_id)

    def get_by_ids(self, location_ids: set[int]) -> dict[int, Location]:
        return {
            location_id: self.locations[location_id]
            for location_id in location_ids
            if location_id in self.locations
        }


def test_creates_event_with_existing_location() -> None:
    result = create_event_and_resolve_location(
        event=Event(
            title="Resolved event",
            organizer="darwin",
            duration_in_minutes=60,
            location_id=4,
        ),
        events=InMemoryEventsRepository(),
        locations=InMemoryLocationsRepository(),
        deletion_delay_minutes=7,
        deletion_delay_when_no_date_in_minutes=9,
        authentication=FakeAuthentication(),
    )

    assert isinstance(result, Event)
    assert result.location_id == 4


def test_creates_location_before_event() -> None:
    result = create_event_and_resolve_location(
        event=Event(
            title="Resolved event",
            organizer="darwin",
            duration_in_minutes=60,
            location=Location(name="New Hall", address="Berlin"),
        ),
        events=InMemoryEventsRepository(),
        locations=InMemoryLocationsRepository(),
        deletion_delay_minutes=7,
        authentication=FakeAuthentication(),
        deletion_delay_when_no_date_in_minutes=9
    )

    assert isinstance(result, Event)
    assert result.location_id == 5


def test_rejects_ambiguous_location_input() -> None:
    with pytest.raises(ValidationError):
        Event(
            title="Resolved event",
            organizer="darwin",
            duration_in_minutes=60,
            location_id=4,
            location=Location(name="New Hall"),
        )
