"""SQLAlchemy implementation of the locations' repository."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, exists, delete

from src.domain.entities import Location
from src.domain.exceptions import EntityNotFoundError
from src.domain.ports.database import LocationsRepository

from .database import SQLAlchemyDatabase
from .mappers import location_model_to_entity
from .models import LocationModel, EventModel

logger = logging.getLogger(__name__)


class SQLAlchemyLocationsRepository(LocationsRepository):
    """Persist locations through SQLAlchemy."""

    def __init__(self, database: SQLAlchemyDatabase) -> None:
        self._database = database

    def create(self, location: Location) -> Location:
        coordinates = location.coordinates
        with self._database.sessions.begin() as session:
            model = LocationModel(
                name=location.name,
                address=location.address,
                country=location.country,
                city=location.city,
                postal_code=location.postal_code,
                latitude=coordinates.latitude if coordinates else None,
                longitude=coordinates.longitude if coordinates else None,
                created_at=location.created_at,
            )
            session.add(model)
            session.flush()
            created_location = location_model_to_entity(model)
            logger.info(
                "Location created",
                extra={
                    "checkpoint_id": "location-created",
                    "location_id": created_location.id,
                },
            )
            return created_location

    def get_by_id(self, location_id: int) -> Optional[Location]:
        """Get Location by id."""
        with self._database.sessions() as session:
            model = session.get(LocationModel, location_id)
            logger.debug(
                "Location lookup completed",
                extra={
                    "checkpoint_id": "location-lookup",
                    "location_id": location_id,
                    "entity_found": model is not None,
                },
            )
            return location_model_to_entity(model) if model is not None else None

    def get_by_ids(self, location_ids: set[int]) -> dict[int, Location]:
        """Get location by ids."""
        if not location_ids:
            return {}
        statement = select(LocationModel).where(
            LocationModel.id.in_(location_ids)
        )
        with self._database.sessions() as session:
            locations = [
                location_model_to_entity(model)
                for model in session.scalars(statement).all()
            ]
            return {location.id: location for location in locations if location.id is not None}

    def get_all(self) -> list[Location]:
        """Get all Locations."""
        statement = select(LocationModel).order_by(LocationModel.id)
        with self._database.sessions() as session:
            return [
                location_model_to_entity(model)
                for model in session.scalars(statement).all()
            ]

    def update(self, location: Location) -> Location:
        """Update location"""
        if location.id is None:
            raise ValueError("Cannot update a location without an id.")
        coordinates = location.coordinates
        with self._database.sessions.begin() as session:
            model = session.get(LocationModel, location.id)
            if model is None:
                raise EntityNotFoundError(
                    f"Location '{location.id}' does not exist."
                )
            model.name = location.name
            model.address = location.address
            model.country = location.country
            model.city = location.city
            model.postal_code = location.postal_code
            model.latitude = coordinates.latitude if coordinates else None
            model.longitude = coordinates.longitude if coordinates else None
            session.flush()
            updated_location = location_model_to_entity(model)
            logger.info(
                "Location updated",
                extra={
                    "checkpoint_id": "location-updated",
                    "location_id": updated_location.id,
                },
            )
            return updated_location

    def delete_old_unused_locations(self, timedelta_in_days: int = 365) -> int:
        """Delete old unused locations."""
        threshold = datetime.now(timezone.utc) - timedelta(days=timedelta_in_days)

        with self._database.sessions().begin() as session:
            locations_to_delete = session.execute(
                select(LocationModel)
                .where(LocationModel.created_at < threshold)
                .where(
                    ~exists(
                        select(EventModel.id).where(
                            EventModel.location_id == LocationModel.id
                        )
                    )
                )
            ).scalars().all()
            if not locations_to_delete:
                logger.debug("There are no locations to delete.")
                return 0
            location_ids = []
            for location in locations_to_delete:
                logger.debug(
                    "Deleting unused location: "
                    f"id={location.id}, "
                    f"name={location.name}, "
                    f"address={location.address}, "
                    f"city={location.city}, "
                    f"country={location.country}, "
                    f"postal_code={location.postal_code}, "
                    f"created_at={location.created_at}"
                )
                location_ids.append(location.id)

            result = session.execute(
                delete(LocationModel).where(LocationModel.id.in_(location_ids))
            )
            return result.rowcount or 0
