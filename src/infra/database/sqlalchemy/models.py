"""SQLAlchemy persistence models kept outside the domain."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    REAL,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .types import UTCDateTime


class Base(DeclarativeBase):
    """Declarative base for persistence-only models."""


class LocationModel(Base):
    """Persisted location record."""

    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint(
            "name IS NULL OR length(trim(name)) BETWEEN 1 AND 200",
            name="ck_locations_name_length",
        ),
        CheckConstraint(
            "address IS NULL OR length(trim(address)) BETWEEN 1 AND 500",
            name="ck_locations_address_length",
        ),
        CheckConstraint(
            "country IS NULL OR "
            "(length(country) = 2 AND country = upper(country))",
            name="ck_locations_country_iso_alpha2",
        ),
        CheckConstraint(
            "city IS NULL OR length(trim(city)) BETWEEN 1 AND 200",
            name="ck_locations_city_length",
        ),
        CheckConstraint(
            "postal_code IS NULL OR "
            "length(trim(postal_code)) BETWEEN 1 AND 32",
            name="ck_locations_postal_code_length",
        ),
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90.0 AND 90.0",
            name="ck_locations_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180.0 AND 180.0",
            name="ck_locations_longitude",
        ),
        CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) "
            "OR (latitude IS NOT NULL AND longitude IS NOT NULL)",
            name="ck_locations_complete_coordinates",
        ),
        CheckConstraint(
            "name IS NOT NULL OR address IS NOT NULL OR latitude IS NOT NULL",
            name="ck_locations_has_description",
        ),
        Index("ix_locations_coordinates", "latitude", "longitude"),
        Index(
            "ix_locations_country_city_postal_code",
            "country",
            "city",
            "postal_code",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(Text)
    address: Mapped[Optional[str]] = mapped_column(Text)
    country: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(Text)
    postal_code: Mapped[Optional[str]] = mapped_column(Text)
    latitude: Mapped[Optional[float]] = mapped_column(REAL)
    longitude: Mapped[Optional[float]] = mapped_column(REAL)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())




class UserModel(Base):
    """Persisted application user."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 64",
            name="ck_users_name_length",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)


Index("ux_users_name_nocase", func.lower(UserModel.name), unique=True)


class EventModel(Base):
    """Persisted event record."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "length(trim(title)) BETWEEN 1 AND 250",
            name="ck_events_title_length",
        ),
        CheckConstraint(
            "duration_in_minutes > 0",
            name="ck_events_positive_duration",
        ),
        CheckConstraint(
            "status IN ('active', 'canceled')",
            name="ck_events_status",
        ),
        CheckConstraint(
            "(status = 'active' AND canceled_at IS NULL) "
            "OR (status = 'canceled' AND canceled_at IS NOT NULL)",
            name="ck_events_cancellation_state",
        ),
        Index("ix_events_organizer_id", "organizer_id"),
        Index("ix_events_location_id", "location_id"),
        Index("ix_events_scheduled_at", "scheduled_at"),
        Index("ix_events_status", "status"),
        Index("ix_events_deletion_scheduled_at", "deletion_scheduled_at"),
        {"sqlite_strict": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    organizer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
    )
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    duration_in_minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    deletion_scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime()
    )
    location_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("locations.id", onupdate="CASCADE", ondelete="RESTRICT"),
    )


class JoinerModel(Base):
    """Persisted event participant."""

    __tablename__ = "joiners"
    __table_args__ = (
        Index("ix_joiners_user_id", "user_id"),
        Index("ix_joiners_event_id", "event_id"),
        Index(
            "ux_joiners_active_user_event",
            "user_id",
            "event_id",
            unique=True,
            sqlite_where=text("left_at IS NULL"),
            postgresql_where=text("left_at IS NULL"),
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("events.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime())
    left_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
