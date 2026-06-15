"""Portable SQLAlchemy type tests."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects import postgresql, sqlite

from src.infra.database.sqlalchemy.types import UTCDateTime


def test_utc_datetime_uses_timezone_timestamp_for_postgresql() -> None:
    dialect = postgresql.dialect()
    column_type = UTCDateTime().dialect_impl(dialect)

    assert "TIMESTAMP WITH TIME ZONE" in str(
        column_type.compile(dialect=dialect)
    )


def test_utc_datetime_uses_iso_utc_text_for_sqlite() -> None:
    column_type = UTCDateTime()
    dialect = sqlite.dialect()
    local_time = datetime(
        2026,
        8,
        20,
        20,
        tzinfo=timezone(timedelta(hours=2)),
    )

    persisted = column_type.process_bind_param(local_time, dialect)
    restored = column_type.process_result_value(persisted, dialect)

    assert persisted == "2026-08-20T18:00:00+00:00"
    assert restored == datetime(2026, 8, 20, 18, tzinfo=timezone.utc)
