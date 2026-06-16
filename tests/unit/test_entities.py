"""Domain entity tests."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.domain.dtos import EventCreate, EventFilters
from src.domain.entities import (
    Event,
    EventStatus,
    GeoPoint,
    Joiner,
    Location,
)
from src.domain.exceptions import DomainValidationError


def test_location_accepts_coordinates_only() -> None:
    location = Location(coordinates=GeoPoint(latitude=52.52, longitude=13.405))

    assert location.name is None
    assert location.address is None
    assert location.coordinates.as_geojson() == {
        "type": "Point",
        "coordinates": [13.405, 52.52],
    }


def test_location_normalizes_country_city_and_postal_code() -> None:
    location = Location(
        address="Gran Via 1",
        country="es",
        city="  MÁLAGA  ",
        postal_code=" 29001 ",
    )

    assert location.country == "ES"
    assert location.city == "malaga"
    assert location.postal_code == "29001"


@pytest.mark.parametrize("country", ["E", "ESP", "3S", "ÉS"])
def test_location_rejects_invalid_country_code(country) -> None:
    with pytest.raises(ValidationError, match="2-character ISO"):
        Location(address="Known address", country=country)


def test_location_rejects_empty_description() -> None:
    with pytest.raises(ValidationError):
        Location()


def test_event_accepts_no_scheduled_date() -> None:
    event = Event(
        title="Date to be defined",
        organizer="darwin",
        scheduled_at=None,
        duration_in_minutes=90,
        location_id=1,
    )

    assert event.scheduled_at is None


def test_event_create_injects_identity_outside_the_public_payload() -> None:
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    schedule_at = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)
    request = EventCreate(
        title=" Public event ",
        duration_in_minutes=60,
        location=Location(address="Remote", created_at=now),
        scheduled_at=schedule_at
    )

    event = request.to_event(organizer="darwin")

    assert event.title == "Public event"
    assert event.organizer == "darwin"
    assert event.location.created_at == now
    assert event.location == Location(address="Remote", created_at=now)
    assert event.scheduled_at == schedule_at


def test_event_create_rejects_client_controlled_organizer() -> None:
    with pytest.raises(ValidationError):
        EventCreate.model_validate(
            {
                "title": "Invalid identity",
                "organizer": "another-user",
                "duration_in_minutes": 60,
                "location": {"address": "Remote"},
            }
        )


def test_event_accepts_berlin_time_and_normalizes_it_to_utc() -> None:
    event = Event.model_validate(
        {
            "title": "Berlin event",
            "organizer": "darwin",
            "scheduled_at": "2026-08-20T18:30:00+02:00",
            "duration_in_minutes": 60,
            "location_id": 1,
        }
    )

    assert event.scheduled_at == datetime(
        2026,
        8,
        20,
        16,
        30,
        tzinfo=timezone.utc,
    )


def test_event_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        Event(
            title="Invalid timezone",
            organizer="darwin",
            scheduled_at=datetime(2026, 6, 11, 18, 0),
            duration_in_minutes=60,
            location_id=1,
        )


def test_event_schedules_deletion_after_end_time() -> None:
    event = Event(
        title="Scheduled event",
        organizer="darwin",
        scheduled_at=datetime(2026, 8, 20, 18, 30, tzinfo=timezone.utc),
        duration_in_minutes=90,
        location_id=1,
    )

    event_with_deletion = event.schedule_deletion_after_event(delay_minutes=7*24*60)

    assert event_with_deletion.status is EventStatus.ACTIVE
    assert event_with_deletion.deletion_scheduled_at == datetime(
        2026,
        8,
        27,
        20,
        0,
        tzinfo=timezone.utc,
    )


def test_unscheduled_event_has_no_deletion_date() -> None:
    event = Event(
        title="Date to be defined",
        organizer="darwin",
        duration_in_minutes=60,
        location_id=1,
    )

    assert event.schedule_deletion_after_event(7).deletion_scheduled_at is None


def test_canceling_future_event_uses_earlier_cancellation_deletion_date() -> None:
    event = Event(
        title="Cancelable event",
        organizer="darwin",
        scheduled_at=datetime(2026, 8, 20, 18, 30, tzinfo=timezone.utc),
        duration_in_minutes=60,
        location_id=1,
    ).schedule_deletion_after_event(7*24*60)
    canceled_at = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

    canceled_event = event.cancel(canceled_at, deletion_delay_minutes=1*24*60)

    assert canceled_event.status is EventStatus.CANCELED
    assert canceled_event.canceled_at == canceled_at
    assert canceled_event.deletion_scheduled_at == datetime(
        2026,
        8,
        11,
        12,
        0,
        tzinfo=timezone.utc,
    )


def test_canceling_past_event_keeps_earlier_event_deletion_date() -> None:
    event = Event(
        title="Past event",
        organizer="darwin",
        scheduled_at=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
        duration_in_minutes=60,
        location_id=1,
    ).schedule_deletion_after_event(7*24*60)
    canceled_at = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

    canceled_event = event.cancel(canceled_at, deletion_delay_minutes=1*24*60)

    assert canceled_event.status is EventStatus.CANCELED
    assert canceled_event.canceled_at == canceled_at
    assert canceled_event.deletion_scheduled_at == datetime(
        2026,
        8,
        8,
        11,
        0,
        tzinfo=timezone.utc,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", " "),
        ("title", "x" * 251),
        ("organizer", ""),
        ("organizer", "x" * 65),
    ],
)
def test_event_rejects_invalid_required_text(field, value) -> None:
    data = {
        "title": "Valid",
        "organizer": "darwin",
        "duration_in_minutes": 60,
        "location_id": 1,
        field: value,
    }

    with pytest.raises(ValidationError):
        Event(**data)


def test_event_rejects_invalid_location_and_cancellation_states() -> None:
    with pytest.raises(ValidationError):
        Event(
            title="No location",
            organizer="darwin",
            duration_in_minutes=60,
        )
    with pytest.raises(ValidationError):
        Event(
            title="Two locations",
            organizer="darwin",
            duration_in_minutes=60,
            location_id=1,
            location=Location(address="Remote"),
        )
    with pytest.raises(ValidationError):
        Event(
            title="Active but canceled",
            organizer="darwin",
            duration_in_minutes=60,
            location_id=1,
            canceled_at=datetime.now(timezone.utc),
        )
    with pytest.raises(ValidationError):
        Event(
            title="Canceled without time",
            organizer="darwin",
            duration_in_minutes=60,
            location_id=1,
            status=EventStatus.CANCELED,
        )


def test_event_rejects_canceling_twice_naive_clock_and_invalid_delays() -> None:
    event = Event(
        title="Cancelable",
        organizer="darwin",
        duration_in_minutes=60,
        location_id=1,
    )
    with pytest.raises(DomainValidationError, match="timezone"):
        event.cancel(datetime(2026, 8, 20), deletion_delay_minutes=1)
    for invalid_delay in (-1, 1.5, True):
        with pytest.raises(DomainValidationError):
            event.schedule_deletion_after_event(invalid_delay)

    canceled = event.cancel(datetime.now(timezone.utc), deletion_delay_minutes=1)
    with pytest.raises(DomainValidationError, match="already canceled"):
        canceled.cancel(datetime.now(timezone.utc), deletion_delay_minutes=1)


def test_filters_reject_empty_name_naive_dates_and_inverted_range() -> None:
    with pytest.raises(ValidationError):
        EventFilters(name=" ")
    with pytest.raises(ValidationError):
        EventFilters(scheduled_from=datetime(2026, 8, 20))
    with pytest.raises(ValidationError):
        EventFilters(
            scheduled_from=datetime(2026, 8, 21, tzinfo=timezone.utc),
            scheduled_until=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )
    with pytest.raises(ValidationError):
        EventFilters(deletion_scheduled_until=datetime(2026, 8, 20))
    with pytest.raises(ValidationError):
        EventFilters(
            deletion_scheduled_from=datetime(
                2026,
                8,
                21,
                tzinfo=timezone.utc,
            ),
            deletion_scheduled_until=datetime(
                2026,
                8,
                20,
                tzinfo=timezone.utc,
            ),
        )


def test_location_and_joiner_enforce_text_limits() -> None:
    with pytest.raises(ValidationError):
        Location(name="x" * 201)
    with pytest.raises(ValidationError):
        Location(address="x" * 501)
    with pytest.raises(ValidationError):
        Location(address="Known address", city="x" * 201)
    with pytest.raises(ValidationError):
        Location(address="Known address", postal_code="x" * 33)
    with pytest.raises(ValidationError):
        Joiner(user_id=1, user_name=" ", event_id=1)
    with pytest.raises(ValidationError):
        Joiner(user_id=1, user_name="x" * 65, event_id=1)
    with pytest.raises(ValidationError):
        Joiner(
            user_id=1,
            user_name="darwin",
            event_id=1,
            left_at=datetime(2026, 8, 20, 12, 0),
        )


def test_event_duration_requires_whole_positive_minutes() -> None:
    with pytest.raises(ValidationError):
        Event(
            title="Fractional minute",
            organizer="darwin",
            duration_in_minutes=1.5,
            location_id=1,
        )
    with pytest.raises(ValidationError):
        Event(
            title="Zero duration",
            organizer="darwin",
            duration_in_minutes=0,
            location_id=1,
        )
