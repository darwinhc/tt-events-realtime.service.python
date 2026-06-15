"""Create-location use case."""

from src.domain.entities import Location
from src.domain.ports.database import LocationsRepository


def create_location(
    location: Location,
    locations: LocationsRepository,
) -> Location:
    """Create a location from any useful combination of location details."""
    return locations.create(location.model_copy(update={"id": None}))
