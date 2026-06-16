"""Delete old unused locations use case"""
import logging
from datetime import datetime, timezone, timedelta

from src.domain.ports.database import LocationsRepository


logger = logging.getLogger(__name__)


def delete_old_unused_locations(
    locations: LocationsRepository,
    timedelta_in_minutes: int = 365,
) -> int:
    """Delete old unused locations to clean up the database"""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=timedelta_in_minutes)
    n_deleted = locations.delete_unused_locations_from_datetime(threshold)
    return n_deleted
