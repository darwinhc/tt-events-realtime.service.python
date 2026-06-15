"""Delete old unused locations use case"""
import logging

from src.domain.ports.database import LocationsRepository


logger = logging.getLogger(__name__)


def delete_old_unused_locations(
    locations: LocationsRepository,
    timedelta_in_days: int = 365,
) -> int:
    """Delete old unused locations to clean up the database"""
    logger.debug(f"Deleting old unused locations in the last {timedelta_in_days} days")
    n_deleted = locations.delete_old_unused_locations(timedelta_in_days=timedelta_in_days)
    if n_deleted:
        logger.debug(f"Deleted {n_deleted} old unused locations")
    return n_deleted
