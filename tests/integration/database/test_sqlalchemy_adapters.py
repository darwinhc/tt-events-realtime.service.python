"""SQLAlchemy adapter integration tests using SQLite."""

from datetime import datetime, timedelta, timezone

import pytest

from src.infra.database.sqlalchemy.models import Base
from src.domain.dtos import EventFilters
from src.domain.entities import (
    Event,
    EventStatus,
    GeoPoint,
    Joiner,
    Location,
)
from src.domain.exceptions import EntityConflictError, EntityNotFoundError
from sqlalchemy import text

from src.infra.database.sqlalchemy import (
    SQLAlchemyDatabase,
    SQLAlchemyEventsRepository,
    SQLAlchemyJoinersRepository,
    SQLAlchemyLocationsRepository,
    SQLAlchemyUsersRepository,
)
from src.domain.entities import User

@pytest.fixture
def database(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'events.db'}"
    database = SQLAlchemyDatabase(database_url)
    Base.metadata.create_all(database.engine)
    yield database
    database.dispose()

@pytest.fixture
def users(database):
    return SQLAlchemyUsersRepository(database)


@pytest.fixture
def locations(database):
    return SQLAlchemyLocationsRepository(database)


@pytest.fixture
def events(database):
    return SQLAlchemyEventsRepository(database)


@pytest.fixture
def joiners(database):
    return SQLAlchemyJoinersRepository(database)

@pytest.fixture
def seed_users(users):
    return {
        "darwin": users.create(User(name="darwin")),
        "external_user": users.create(User(name="external-user")),
        "another_user": users.create(User(name="another-user")),
        "organizer_from_identity": users.create(
            User(name="organizer-from-identity-service")
        ),
    }


def test_persists_event_with_references_and_exact_duration(database, locations, events, seed_users) -> None:
    location = locations.create(
        Location(
            name="Main Hall",
            address="Alexanderplatz 1, Berlin",
            country="de",
            city="BÉRLIN",
            postal_code="10178",
            coordinates=GeoPoint(latitude=52.5219, longitude=13.4132),
        )
    )
    scheduled_at = datetime(2026, 8, 20, 18, 30, tzinfo=timezone.utc)

    created = events.create(
        Event(
            title="Realtime Systems Meetup",
            organizer="darwin",
            organizer_id=1,
            scheduled_at=scheduled_at,
            duration_in_minutes=105,
            location_id=location.id,
        )
    )

    persisted = events.get_by_id(created.id)
    assert persisted == created
    assert location.country == "DE"
    assert location.city == "berlin"
    assert location.postal_code == "10178"
    with database.engine.connect() as connection:
        stored_minutes = connection.execute(
            text("SELECT duration_in_minutes FROM events WHERE id = :event_id"),
            {"event_id": created.id},
        ).scalar_one()
    assert stored_minutes == 105


def test_persists_date_to_be_defined_event(locations, events, seed_users) -> None:
    location = locations.create(Location(address="Remote"))

    created = events.create(
        Event(
            title="Planning session",
            organizer="organizer-from-identity-service",
            organizer_id=seed_users["organizer_from_identity"].id,
            scheduled_at=None,
            duration_in_minutes=120,
            location_id=location.id,
        )
    )

    assert events.get_by_id(created.id).scheduled_at is None


def test_accepts_external_organizer_without_local_user(database, locations, events, seed_users) -> None:
    location = locations.create(Location(address="Remote"))

    created = events.create(
        Event(
            title="External organizer",
            organizer="nickname-from-another-service",
            organizer_id=seed_users["organizer_from_identity"].id,
            duration_in_minutes=60,
            location_id=location.id,
        )
    )

    assert created.organizer == "nickname-from-another-service"


def test_rejects_event_with_unknown_location(database, locations, events, seed_users) -> None:
    with pytest.raises(EntityNotFoundError):
        events.create(
            Event(
                title="Invalid location",
                organizer="external-organizer",
                organizer_id=seed_users["organizer_from_identity"].id,
                duration_in_minutes=60,
                location_id=999,
            )
        )


def test_updates_canceled_event_and_deletes_it_when_due(database, locations, events, seed_users) -> None:
    location = locations.create(Location(address="Remote"))
    created = events.create(
        Event(
            title="Short-lived event",
            organizer="darwin",
            organizer_id=seed_users["darwin"].id,
            duration_in_minutes=60,
            location_id=location.id,
        )
    )
    canceled_at = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

    canceled = events.update(created.cancel(canceled_at, deletion_delay_minutes=1*24*60))

    assert events.delete_due(canceled_at + timedelta(hours=23)) == 0
    assert events.get_by_id(created.id) == canceled
    assert events.delete_due(canceled_at + timedelta(minutes=1*24*60)) == 1
    assert events.get_by_id(created.id) is None


def test_get_all_filters_events(database, locations, events, seed_users) -> None:
    berlin = locations.create(Location(name="Berlin Hall"))
    hamburg = locations.create(Location(name="Hamburg Hall"))
    realtime = events.create(
        Event(
            title="Realtime Systems Meetup",
            organizer="darwin",
            organizer_id=1,
            scheduled_at=datetime(
                2026,
                8,
                20,
                18,
                30,
                tzinfo=timezone.utc,
            ),
            duration_in_minutes=60,
            location_id=berlin.id,
        )
    )
    canceled = events.create(
        Event(
            title="Realtime Planning",
            organizer="darwin",
            organizer_id=1,
            scheduled_at=datetime(
                2026,
                8,
                21,
                10,
                0,
                tzinfo=timezone.utc,
            ),
            duration_in_minutes=60,
            location_id=berlin.id,
        )
    )
    events.update(
        canceled.cancel(
            datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
            deletion_delay_minutes=1,
        )
    )
    events.create(
        Event(
            title="Realtime Systems Meetup",
            organizer="darwin",
            organizer_id=1,
            scheduled_at=datetime(
                2026,
                8,
                20,
                18,
                30,
                tzinfo=timezone.utc,
            ),
            duration_in_minutes=60,
            location_id=hamburg.id,
        )
    )
    events.create(
        Event(
            title="Unscheduled Realtime Session",
            organizer="darwin",
            organizer_id=1,
            duration_in_minutes=60,
            location_id=berlin.id,
        )
    )

    filtered = events.get_all(
        EventFilters(
            statuses=(EventStatus.ACTIVE, EventStatus.CANCELED),
            name="systems",
            scheduled_from=datetime(
                2026,
                8,
                20,
                tzinfo=timezone.utc,
            ),
            scheduled_until=datetime(
                2026,
                8,
                21,
                tzinfo=timezone.utc,
            ),
            location_id=berlin.id,
        )
    )

    assert filtered == [realtime]


def test_get_all_filters_by_single_or_multiple_statuses(locations, events, seed_users) -> None:
    location = locations.create(Location(address="Remote"))
    active = events.create(
        Event(
            title="Active event",
            organizer="darwin",
            organizer_id=seed_users["darwin"].id,
            duration_in_minutes=60,
            location_id=location.id,
        )
    )
    canceled = events.create(
        Event(
            title="Canceled event",
            organizer="darwin",
            organizer_id=seed_users["darwin"].id,
            duration_in_minutes=60,
            location_id=location.id,
        )
    )
    canceled = events.update(
        canceled.cancel(
            datetime(2026, 8, 10, tzinfo=timezone.utc),
            deletion_delay_minutes=1,
        )
    )

    assert events.get_all(
        EventFilters(statuses=(EventStatus.CANCELED,))
    ) == [canceled]
    assert events.get_all(
        EventFilters(
            statuses=(EventStatus.ACTIVE, EventStatus.CANCELED)
        )
    ) == [active, canceled]
    assert events.get_all() == [active, canceled]


def test_get_all_filters_by_deletion_date_range(locations, seed_users, events) -> None:
    location = locations.create(Location(address="Remote"))
    before_range = events.create(
        Event(
            title="Before range",
            organizer="darwin",
            organizer_id=seed_users["darwin"].id,
            duration_in_minutes=60,
            location_id=location.id,
            deletion_scheduled_at=datetime(
                2026,
                8,
                10,
                tzinfo=timezone.utc,
            ),
        )
    )
    in_range = events.create(
        Event(
            title="In range",
            organizer="darwin",
            organizer_id=seed_users["darwin"].id,
            duration_in_minutes=60,
            location_id=location.id,
            deletion_scheduled_at=datetime(
                2026,
                8,
                20,
                tzinfo=timezone.utc,
            ),
        )
    )
    at_exclusive_end = events.create(
        Event(
            title="At exclusive end",
            organizer="darwin",
            organizer_id=seed_users["organizer_from_identity"].id,
            duration_in_minutes=60,
            location_id=location.id,
            deletion_scheduled_at=datetime(
                2026,
                9,
                1,
                tzinfo=timezone.utc,
            ),
        )
    )
    events.create(
        Event(
            title="Without deletion date",
            organizer="darwin",
            organizer_id=seed_users["organizer_from_identity"].id,
            duration_in_minutes=60,
            location_id=location.id,
        )
    )

    filtered = events.get_all(
        EventFilters(
            deletion_scheduled_from=datetime(
                2026,
                8,
                10,
                0,
                0,
                1,
                tzinfo=timezone.utc,
            ),
            deletion_scheduled_until=datetime(
                2026,
                9,
                1,
                tzinfo=timezone.utc,
            ),
        )
    )

    assert before_range not in filtered
    assert filtered == [in_range]
    assert at_exclusive_end not in filtered


def test_persists_leaves_and_rejoins_with_joiner_history(locations, joiners, users, events, database, seed_users) -> None:
    location = locations.create(Location(address="Remote"))
    event = events.create(
        Event(
            title="Joinable event",
            organizer="darwin",
            organizer_id=seed_users["organizer_from_identity"].id,
            duration_in_minutes=60,
            location_id=location.id,
        )
    )
    joiner = Joiner(
        user_id=seed_users["external_user"].id,
        user_name=seed_users["external_user"].name,
        event_id=event.id,
    )

    created_joiner = joiners.create(joiner)
    assert created_joiner.id == 1
    assert created_joiner.left_at is None
    assert joiners.get(joiner.user_id, joiner.event_id) == created_joiner
    second_joiner = joiners.create(
        Joiner(
            user_id=seed_users["another_user"].id,
            user_name=seed_users["another_user"].name,
            event_id=event.id,
        )
    )
    assert joiners.count_by_event(event.id) == 2
    assert joiners.count_by_events({event.id, 999}) == {event.id: 2}
    assert joiners.get_all_by_event(event.id) == [
        second_joiner,
        created_joiner,
    ]
    with pytest.raises(EntityConflictError):
        joiners.create(joiner)

    left_at = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
    left_joiner = joiners.leave(
        joiner.user_id,
        joiner.event_id,
        left_at,
    )

    assert left_joiner.id == created_joiner.id
    assert left_joiner.left_at == left_at
    assert joiners.get(joiner.user_id, joiner.event_id) is None
    assert joiners.count_by_event(event.id) == 1

    rejoined = joiners.create(joiner)

    assert rejoined.id != created_joiner.id
    assert rejoined.left_at is None
    assert joiners.get(joiner.user_id, joiner.event_id) == rejoined
    with database.engine.connect() as connection:
        history = connection.execute(
            text(
                "SELECT id, left_at FROM joiners "
                "WHERE user_id = :user_id AND event_id = :event_id "
                "ORDER BY id"
            ),
            {"user_id": joiner.user_id, "event_id": joiner.event_id},
        ).all()
    assert history == [
        (created_joiner.id, left_at.isoformat()),
        (rejoined.id, None),
    ]


def test_event_deletion_cascades_to_joiners(locations, users, events, database, joiners, seed_users) -> None:
    location = locations.create(Location(address="Remote"))
    created = events.create(
        Event(
            title="Expiring event",
            organizer="darwin",
            organizer_id=1,
            duration_in_minutes=60,
            location_id=location.id,
        )
    )
    canceled_at = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    events.update(created.cancel(canceled_at, deletion_delay_minutes=1))

    joiner = joiners.create(
        Joiner(
            user_id=seed_users["external_user"].id,
            user_name=seed_users["external_user"].name,
            event_id=created.id,
        )
    )

    assert events.delete_due(canceled_at + timedelta(minutes=1)) == 1
    assert joiners.get(joiner.user_id, joiner.event_id) is None
    with database.engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT COUNT(*) FROM joiners WHERE event_id = :event_id"
            ),
            {"event_id": created.id},
        ).scalar_one() == 0


def test_repository_rejects_invalid_update_and_naive_deletion_cutoff(
    events, seed_users,
) -> None:
    with pytest.raises(ValueError, match="without an id"):
        events.update(
            Event(
                title="Not persisted",
                organizer="darwin",
                organizer_id=seed_users["organizer_from_identity"].id,
                duration_in_minutes=60,
                location_id=1,
            )
        )
    with pytest.raises(ValueError, match="timezone"):
        events.delete_due(datetime(2026, 8, 20, 12, 0))


def test_joiner_repository_handles_missing_and_empty_queries(locations, users, joiners, database, seed_users) -> None:
    location = locations.create(Location(address="Remote"))
    user = users.create(User(name="guest"))
    with pytest.raises(EntityNotFoundError):
        joiners.create(
            Joiner(user_id=user.id, user_name=user.name, event_id=999)
        )
    assert joiners.count_by_events(set()) == {}
    assert (
        joiners.leave(
            user_id=999,
            event_id=999,
            left_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )
        is None
    )
    with pytest.raises(ValueError, match="timezone"):
        joiners.leave(user_id=user.id, event_id=999, left_at=datetime(2026, 8, 20))
