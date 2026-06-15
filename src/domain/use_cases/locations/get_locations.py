"""Get-locations use case."""

from src.domain.entities import Location
from src.domain.ports.database import LocationsRepository


def get_locations(locations: LocationsRepository) -> list[Location]:
    """Return all persisted locations."""
    return locations.get_all()
