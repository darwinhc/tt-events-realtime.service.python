"""Portable SQLAlchemy persistence types."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Text
from sqlalchemy.types import TypeDecorator

# pylint: disable=too-many-ancestors,abstract-method

class UTCDateTime(TypeDecorator):
    """Persist aware UTC datetime with dialect-appropriate storage."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(Text())
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Persisted datetimes must include a timezone.")
        normalized = value.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            return normalized.isoformat()
        return normalized

    def process_result_value(self, value, _dialect):
        if value is None:
            return None
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
