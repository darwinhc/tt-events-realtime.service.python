"""Delete old unused locations use case"""
import logging
from datetime import datetime, timezone, timedelta

from src.domain.ports.database import LocationsRepository


logger = logging.getLogger(__name__)


def delete_old_unused_locations(
    locations: LocationsRepository,
    timedelta_in_days: int = 365,
) -> int:
    """Delete old unused locations to clean up the database"""
    logger.debug(f"Deleting old unused locations in the last {timedelta_in_days} days")
    threshold = datetime.now(timezone.utc) - timedelta(days=timedelta_in_days)
    n_deleted = locations.delete_unused_locations_from_datetime(threshold)
    if n_deleted:
        logger.debug(f"Deleted {n_deleted} old unused locations")
    return n_deleted
