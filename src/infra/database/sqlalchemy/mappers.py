"""Mappings between ORM records and pure domain entities."""

from src.domain.entities import Event, EventStatus, GeoPoint, Joiner, Location, User

from .models import EventModel, JoinerModel, LocationModel, UserModel


def location_model_to_entity(model: LocationModel) -> Location:
    """Map a location persistence model to the domain."""
    coordinates = None
    if model.latitude is not None and model.longitude is not None:
        coordinates = GeoPoint(
            latitude=model.latitude,
            longitude=model.longitude,
        )
    return Location(
        id=model.id,
        name=model.name,
        address=model.address,
        country=model.country,
        city=model.city,
        postal_code=model.postal_code,
        coordinates=coordinates,
    )


def user_model_to_entity(model: UserModel) -> User:
    """Map a user persistence model to the domain."""
    return User(id=model.id, name=model.name)


def event_model_to_entity(model: EventModel, organizer_name: str) -> Event:
    """Map an event persistence model to the domain."""
    return Event(
        id=model.id,
        title=model.title,
        organizer=organizer_name,
        organizer_id=model.organizer_id,
        scheduled_at=model.scheduled_at,
        duration_in_minutes=model.duration_in_minutes,
        location_id=model.location_id,
        status=EventStatus(model.status),
        canceled_at=model.canceled_at,
        deletion_scheduled_at=model.deletion_scheduled_at,
    )


def joiner_model_to_entity(model: JoinerModel, user_name: str) -> Joiner:
    """Map a joiner persistence model to the domain."""
    return Joiner(
        id=model.id,
        user_id=model.user_id,
        user_name=user_name,
        event_id=model.event_id,
        left_at=model.left_at,
    )
