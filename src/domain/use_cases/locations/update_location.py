"""Update-location use case."""

from src.domain.dtos import LocationUpdate
from src.domain.entities import Location, RealtimeEvent
from src.domain.exceptions import EntityNotFoundError
from src.domain.ports.database import LocationsRepository
from src.domain.ports.events import (
    NullRealtimeEventPublisher,
    RealtimeEventPublisher,
)


def update_location(
    location_id: int,
    changes: LocationUpdate,
    locations: LocationsRepository,
    realtime: RealtimeEventPublisher = NullRealtimeEventPublisher(),
) -> Location:
    """Update a location and notify global and affected-event subscribers."""
    location = locations.get_by_id(location_id)
    if location is None:
        raise EntityNotFoundError(f"Location '{location_id}' does not exist.")

    persisted_location = locations.update(changes.apply_to(location))
    realtime.publish(
        RealtimeEvent(
            type="location.updated",
            location_id=persisted_location.id,
            payload=persisted_location.model_dump(mode="json"),
        )
    )
    return persisted_location
