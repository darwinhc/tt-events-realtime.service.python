"""SQLAlchemy adapter integration tests using SQLite."""

from datetime import datetime, timedelta, timezone

import pytest

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
def adapters(tmp_path):
    database = SQLAlchemyDatabase(f"sqlite:///{tmp_path / 'events.db'}")
    database.initialize()
    users = SQLAlchemyUsersRepository(database)
    users.create(User(name="darwin"))
    users.create(User(name="organizer-from-identity-service"))
    users.create(User(name="nickname-from-another-service"))
    users.create(User(name="external-organizer"))
    yield (
        SQLAlchemyLocationsRepository(database),
        users,
        SQLAlchemyEventsRepository(database),
        database,
    )
    database.dispose()


def test_persists_event_with_references_and_exact_duration(adapters) -> None:
    locations, _, events, database = adapters
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


def test_database_adds_location_search_fields_to_legacy_table(tmp_path) -> None:
    database = SQLAlchemyDatabase(f"sqlite:///{tmp_path / 'legacy.db'}")
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE locations ("
                "id INTEGER PRIMARY KEY, "
                "name TEXT, address TEXT, latitude REAL, longitude REAL"
                ") STRICT"
            )
        )
        connection.execute(
            text(
                "INSERT INTO locations "
                "(id, name, address, latitude, longitude) "
                "VALUES (1, 'Legacy Hall', NULL, NULL, NULL)"
            )
        )

    database.initialize()

    with database.engine.connect() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(locations)"))
        }
        indexes = {
            row[1]
            for row in connection.execute(text("PRAGMA index_list(locations)"))
        }
        location = connection.execute(
            text(
                "SELECT id, country, city, postal_code "
                "FROM locations WHERE id = 1"
            )
        ).one()
    database.dispose()

    assert {"country", "city", "postal_code"}.issubset(columns)
    assert "ix_locations_country_city_postal_code" in indexes
    assert tuple(location) == (1, None, None, None)


def test_persists_date_to_be_defined_event(adapters) -> None:
    locations, _, events, _ = adapters
    location = locations.create(Location(address="Remote"))

    created = events.create(
        Event(
            title="Planning session",
            organizer="organizer-from-identity-service",
            organizer_id=2,
            scheduled_at=None,
            duration_in_minutes=120,
            location_id=location.id,
        )
    )

    assert events.get_by_id(created.id).scheduled_at is None


def test_accepts_external_organizer_without_local_user(adapters) -> None:
    locations, _, events, _ = adapters
    location = locations.create(Location(address="Remote"))

    created = events.create(
        Event(
            title="External organizer",
            organizer="nickname-from-another-service",
            organizer_id=3,
            duration_in_minutes=60,
            location_id=location.id,
        )
    )

    assert created.organizer == "nickname-from-another-service"


def test_rejects_event_with_unknown_location(adapters) -> None:
    _, _, events, _ = adapters

    with pytest.raises(EntityNotFoundError):
        events.create(
            Event(
                title="Invalid location",
                organizer="external-organizer",
                organizer_id=4,
                duration_in_minutes=60,
                location_id=999,
            )
        )


def test_updates_canceled_event_and_deletes_it_when_due(adapters) -> None:
    locations, _, events, _ = adapters
    location = locations.create(Location(address="Remote"))
    created = events.create(
        Event(
            title="Short-lived event",
            organizer="darwin",
            organizer_id=1,
            duration_in_minutes=60,
            location_id=location.id,
        )
    )
    canceled_at = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

    canceled = events.update(created.cancel(canceled_at, deletion_delay_minutes=1))

    assert events.delete_due(canceled_at + timedelta(hours=23)) == 0
    assert events.get_by_id(created.id) == canceled
    assert events.delete_due(canceled_at + timedelta(days=1)) == 1
    assert events.get_by_id(created.id) is None


def test_get_all_filters_events(adapters) -> None:
    locations, _, events, _ = adapters
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


def test_get_all_filters_by_single_or_multiple_statuses(adapters) -> None:
    locations, _, events, _ = adapters
    location = locations.create(Location(address="Remote"))
    active = events.create(
        Event(
            title="Active event",
            organizer="darwin",
            organizer_id=1,
            duration_in_minutes=60,
            location_id=location.id,
        )
    )
    canceled = events.create(
        Event(
            title="Canceled event",
            organizer="darwin",
            organizer_id=1,
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


def test_get_all_filters_by_deletion_date_range(adapters) -> None:
    locations, _, events, _ = adapters
    location = locations.create(Location(address="Remote"))
    before_range = events.create(
        Event(
            title="Before range",
            organizer="darwin",
            organizer_id=1,
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
            organizer_id=1,
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
            organizer_id=1,
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
            organizer_id=1,
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


def test_persists_leaves_and_rejoins_with_joiner_history(adapters) -> None:
    locations, users, events, database = adapters
    joiners = SQLAlchemyJoinersRepository(database)
    location = locations.create(Location(address="Remote"))
    event = events.create(
        Event(
            title="Joinable event",
            organizer="darwin",
            organizer_id=1,
            duration_in_minutes=60,
            location_id=location.id,
        )
    )
    external_user = users.create(User(name="external-user"))
    another_user = users.create(User(name="another-user"))
    joiner = Joiner(
        user_id=external_user.id,
        user_name=external_user.name,
        event_id=event.id,
    )

    created_joiner = joiners.create(joiner)
    assert created_joiner.id == 1
    assert created_joiner.left_at is None
    assert joiners.get(joiner.user_id, joiner.event_id) == created_joiner
    second_joiner = joiners.create(
        Joiner(
            user_id=another_user.id,
            user_name=another_user.name,
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


def test_event_deletion_cascades_to_joiners(adapters) -> None:
    locations, users, events, database = adapters
    joiners = SQLAlchemyJoinersRepository(database)
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
    external_user = users.create(User(name="external-user"))
    joiner = joiners.create(
        Joiner(
            user_id=external_user.id,
            user_name=external_user.name,
            event_id=created.id,
        )
    )

    assert events.delete_due(canceled_at + timedelta(days=1)) == 1
    assert joiners.get(joiner.user_id, joiner.event_id) is None
    with database.engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT COUNT(*) FROM joiners WHERE event_id = :event_id"
            ),
            {"event_id": created.id},
        ).scalar_one() == 0


def test_repository_rejects_invalid_update_and_naive_deletion_cutoff(
    adapters,
) -> None:
    _, _, events, _ = adapters

    with pytest.raises(ValueError, match="without an id"):
        events.update(
            Event(
                title="Not persisted",
                organizer="darwin",
                organizer_id=1,
                duration_in_minutes=60,
                location_id=1,
            )
        )
    with pytest.raises(ValueError, match="timezone"):
        events.delete_due(datetime(2026, 8, 20, 12, 0))


def test_joiner_repository_handles_missing_and_empty_queries(adapters) -> None:
    _, users, _, database = adapters
    joiners = SQLAlchemyJoinersRepository(database)

    with pytest.raises(EntityNotFoundError):
        user = users.create(User(name="guest"))
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


def test_database_migrates_legacy_seconds_to_minutes(tmp_path) -> None:
    database = SQLAlchemyDatabase(f"sqlite:///{tmp_path / 'legacy.db'}")
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE events ("
                "id INTEGER PRIMARY KEY, "
                "duration_in_seconds INTEGER NOT NULL"
                ") STRICT"
            )
        )
        connection.execute(
            text(
                "INSERT INTO events (id, duration_in_seconds) "
                "VALUES (1, 5400), (2, 10800)"
            )
        )

    database.initialize()

    with database.engine.connect() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(events)"))
        }
        durations = connection.execute(
            text(
                "SELECT duration_in_minutes FROM events ORDER BY id"
            )
        ).scalars().all()
    database.dispose()

    assert "duration_in_minutes" in columns
    assert "duration_in_seconds" not in columns
    assert durations == [90, 180]


def test_database_refuses_legacy_partial_minutes(tmp_path) -> None:
    database = SQLAlchemyDatabase(f"sqlite:///{tmp_path / 'legacy.db'}")
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE events ("
                "id INTEGER PRIMARY KEY, "
                "duration_in_seconds INTEGER NOT NULL"
                ") STRICT"
            )
        )
        connection.execute(
            text(
                "INSERT INTO events (id, duration_in_seconds) "
                "VALUES (1, 61)"
            )
        )

    with pytest.raises(RuntimeError, match="partial minutes"):
        database.initialize()

    database.dispose()


def test_database_migrates_composite_joiners_to_history(tmp_path) -> None:
    database = SQLAlchemyDatabase(f"sqlite:///{tmp_path / 'legacy.db'}")
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, name TEXT NOT NULL"
                ") STRICT"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE events ("
                "id INTEGER PRIMARY KEY, organizer_id INTEGER NOT NULL"
                ") STRICT"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE joiners ("
                "user_id INTEGER NOT NULL, event_id INTEGER NOT NULL, "
                "PRIMARY KEY (user_id, event_id)"
                ") STRICT"
            )
        )
        connection.execute(text("INSERT INTO users VALUES (1, 'guest')"))
        connection.execute(text("INSERT INTO events VALUES (1, 1)"))
        connection.execute(text("INSERT INTO joiners VALUES (1, 1)"))

    database.initialize()

    with database.engine.connect() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(joiners)"))
        }
        migrated = connection.execute(
            text("SELECT id, user_id, event_id, left_at FROM joiners")
        ).one()
        indexes = {
            row[1]
            for row in connection.execute(text("PRAGMA index_list(joiners)"))
        }
    database.dispose()

    assert columns == {"id", "user_id", "event_id", "left_at"}
    assert tuple(migrated) == (1, 1, 1, None)
    assert "ux_joiners_active_user_event" in indexes


def test_database_migrates_text_users_to_integer_foreign_keys(
    tmp_path,
) -> None:
    database = SQLAlchemyDatabase(f"sqlite:///{tmp_path / 'legacy.db'}")
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE locations ("
                "id INTEGER PRIMARY KEY, "
                "name TEXT, address TEXT, latitude REAL, longitude REAL"
                ") STRICT"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE events ("
                "id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
                "organizer TEXT NOT NULL, scheduled_at TEXT, "
                "duration_in_minutes INTEGER NOT NULL, "
                "status TEXT NOT NULL, canceled_at TEXT, "
                "deletion_scheduled_at TEXT, location_id INTEGER NOT NULL"
                ") STRICT"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE joiners ("
                "user_id TEXT NOT NULL, event_id INTEGER NOT NULL, "
                "PRIMARY KEY (user_id, event_id)"
                ") STRICT"
            )
        )
        connection.execute(
            text(
                "INSERT INTO locations "
                "(id, name, address, latitude, longitude) "
                "VALUES (1, 'Main Hall', NULL, NULL, NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO events ("
                "id, title, organizer, scheduled_at, "
                "duration_in_minutes, status, canceled_at, "
                "deletion_scheduled_at, location_id"
                ") VALUES ("
                "1, 'Legacy event', 'Darwin', NULL, "
                "90, 'active', NULL, NULL, 1"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO joiners (user_id, event_id) "
                "VALUES ('Sofia', 1)"
            )
        )

    database.initialize()

    with database.engine.connect() as connection:
        users = connection.execute(
            text("SELECT id, name FROM users ORDER BY id")
        ).all()
        event_row = connection.execute(
            text("SELECT organizer_id FROM events WHERE id = 1")
        ).one()
        joiner_row = connection.execute(
            text("SELECT id, user_id, event_id, left_at FROM joiners")
        ).one()
        event_foreign_keys = connection.execute(
            text("PRAGMA foreign_key_list(events)")
        ).all()
        joiner_foreign_keys = connection.execute(
            text("PRAGMA foreign_key_list(joiners)")
        ).all()
        violations = connection.execute(
            text("PRAGMA foreign_key_check")
        ).all()
    database.dispose()

    users_by_name = {name: user_id for user_id, name in users}
    assert users_by_name == {"Darwin": 1, "Sofia": 2}
    assert event_row.organizer_id == users_by_name["Darwin"]
    assert joiner_row.user_id == users_by_name["Sofia"]
    assert joiner_row.event_id == 1
    assert joiner_row.id == 1
    assert joiner_row.left_at is None
    assert {
        (row[2], row[3], row[4])
        for row in event_foreign_keys
    } >= {("users", "organizer_id", "id")}
    assert {
        (row[2], row[3], row[4])
        for row in joiner_foreign_keys
    } >= {
        ("users", "user_id", "id"),
        ("events", "event_id", "id"),
    }
    assert violations == []
