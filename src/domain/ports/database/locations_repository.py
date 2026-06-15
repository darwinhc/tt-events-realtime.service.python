"""Location repository port."""

from abc import abstractmethod
from datetime import datetime
from typing import Optional

from src.domain.entities import Location

from .repository import Repository


class LocationsRepository(Repository):
    """Technology-neutral persistence operations for locations."""

    @abstractmethod
    def create(self, location: Location) -> Location:
        """Persist and return a location with its generated id."""
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, location_id: int) -> Optional[Location]:
        """Return a location by id, if present."""
        raise NotImplementedError

    @abstractmethod
    def get_by_ids(self, location_ids: set[int]) -> dict[int, Location]:
        """Return locations indexed by id."""
        raise NotImplementedError

    def get_all(self) -> list[Location]:
        """Return all locations in stable id order."""
        raise NotImplementedError

    def update(self, location: Location) -> Location:
        """Persist and return to an existing location."""
        raise NotImplementedError

    def delete_unused_locations_from_datetime(self, threshold: datetime) -> int:
        """Delete all locations older than the given datetime."""
        raise NotImplementedError
