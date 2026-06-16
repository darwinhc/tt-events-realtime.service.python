"""Delete unused locations."""

import logging

from src.domain.use_cases import delete_old_unused_locations
from src.entrypoints.jobs.initialize_job import initialize_job
from src.infra.config.utils import read_non_negative_int
from src.infra.database.sqlalchemy import SQLAlchemyLocationsRepository
from src.infra.database.sqlalchemy.database import SQLAlchemyDatabase

logger = logging.getLogger(__name__)


def main() -> None:
    """Delete unused locations."""
    current_settings = initialize_job()

    # 3 months by default
    timedelta_in_mins = read_non_negative_int("TIMEDELTA_IN_MINUTES", 129600)


    database = SQLAlchemyDatabase(
        current_settings.database_url,
        echo=current_settings.sqlalchemy_echo,
    )
    database.initialize()
    locations = SQLAlchemyLocationsRepository(database)

    deleted_count = delete_old_unused_locations(locations, timedelta_in_minutes=timedelta_in_mins)

    database.dispose()
    logger.info("Unused locations deleted: %s", deleted_count)


if __name__ == "__main__":
    main()
