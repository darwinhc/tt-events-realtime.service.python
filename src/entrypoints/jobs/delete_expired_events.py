"""Delete expired events job."""

import logging
from datetime import datetime, timezone

from src.entrypoints.jobs.initialize_job import initialize_job
from src.infra.database.sqlalchemy import SQLAlchemyEventsRepository
from src.infra.database.sqlalchemy.database import SQLAlchemyDatabase
from src.domain.use_cases.events.delete_expired_events import delete_expired_events

logger = logging.getLogger("JOB_DELETED_EXPIRED_EVENTS")


def main() -> None:
    """Delete expired events."""
    current_settings = initialize_job()

    database = SQLAlchemyDatabase(
        current_settings.database_url,
        echo=current_settings.sqlalchemy_echo,
    )
    database.initialize()
    events = SQLAlchemyEventsRepository(database)

    deleted_count = delete_expired_events(events, lambda: datetime.now(timezone.utc))

    database.dispose()
    logger.info("Expired events deleted: %s", deleted_count)


if __name__ == "__main__":
    main()
