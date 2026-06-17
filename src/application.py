"""Application composition root."""

from functools import lru_cache, partial
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict

from .domain.dtos.joiner_info import JoinerInfo
from .domain.use_cases.get_joiners_for_events import get_joiners_for_events
from .domain.dtos import EventDetails, EventPage
from .domain.entities import Event, Joiner, Location, User
from .infra.auth import SimpleNameAuthentication
from .domain.use_cases import (
    cancel_event,
    create_event,
    create_event_and_resolve_location,
    create_location,
    delete_expired_events,
    get_all_guests,
    get_event,
    get_events,
    get_non_expired_events,
    get_locations,
    get_visible_events,
    join_event,
    leave_event,
    uncancel_event,
    update_event,
    update_location,
    delete_old_unused_locations,
)
from .domain.ports.events import (
    NullRealtimeEventPublisher,
    RealtimeEventPublisher,
)
from .infra.config import Settings, get_settings
from .infra.database.sqlalchemy import (
    SQLAlchemyDatabase,
    SQLAlchemyEventsRepository,
    SQLAlchemyJoinersRepository,
    SQLAlchemyLocationsRepository,
    SQLAlchemyUsersRepository,
)
from .infra.logging import configure_logging, get_logger


class Application(BaseModel):
    """Configured application services exposed to entry-point adapters."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    create_location: Callable[..., Location]
    get_locations: Callable[..., list[Location]]
    update_location: Callable[..., Location]
    delete_old_unused_locations: Callable[..., int]
    authenticate: Callable[..., User]
    create_event: Callable[..., Event]
    create_event_and_resolve_location: Callable[..., Event]
    get_event: Callable[..., EventDetails]
    get_visible_events: Callable[..., list[EventDetails]]
    get_joiners_for_events: Callable[..., list[JoinerInfo]]
    get_events: Callable[..., list[EventDetails]]
    get_non_expired_events: Callable[..., EventPage]
    cancel_event: Callable[..., Event]
    uncancel_event: Callable[..., Event]
    update_event: Callable[..., Event]
    join_event: Callable[..., Joiner]
    leave_event: Callable[..., Joiner]
    get_all_guests: Callable[..., list[Joiner]]
    delete_expired_events: Callable[..., int]
    realtime: RealtimeEventPublisher
    database: SQLAlchemyDatabase


def build_application(
    settings: Optional[Settings] = None,
    realtime: Optional[RealtimeEventPublisher] = None,
) -> Application:
    """Build the application with concrete infrastructure adapters."""
    current_settings = settings or get_settings()
    realtime_publisher = realtime or NullRealtimeEventPublisher()
    configure_logging(current_settings)
    logger = get_logger(__name__)
    logger.info(
        "Starting application setup",
        extra={"checkpoint_id": "application-setup-start"},
    )

    database = SQLAlchemyDatabase(
        current_settings.database_url,
        echo=current_settings.sqlalchemy_echo,
    )
    locations = SQLAlchemyLocationsRepository(database)
    users = SQLAlchemyUsersRepository(database)
    authentication = SimpleNameAuthentication(users)
    events = SQLAlchemyEventsRepository(database)
    joiners = SQLAlchemyJoinersRepository(database)

    application = Application(
        authenticate=authentication.authenticate,
        create_location=partial(create_location, locations=locations),
        get_locations=partial(get_locations, locations=locations),
        update_location=partial(
            update_location,
            locations=locations,
            realtime=realtime_publisher,
        ),
        delete_old_unused_locations=partial(
            delete_old_unused_locations,
            locations=locations,
            timedelta_in_minutes=current_settings.location_unused_deletion_delay_minutes
        ),
        create_event=partial(
            create_event,
            events=events,
            deletion_delay_minutes=current_settings.event_deletion_delay_minutes,
            deletion_delay_when_no_date_in_minutes=current_settings.event_deletion_delay_when_no_date_in_minutes,
            authentication=authentication,
            realtime=realtime_publisher,
        ),
        create_event_and_resolve_location=partial(
            create_event_and_resolve_location,
            events=events,
            locations=locations,
            deletion_delay_minutes=current_settings.event_deletion_delay_minutes,
            deletion_delay_when_no_date_in_minutes=current_settings.event_deletion_delay_when_no_date_in_minutes,
            authentication=authentication,
            realtime=realtime_publisher,
        ),
        get_events=partial(
            get_events,
            events=events,
            locations=locations,
            joiners=joiners,
        ),
        get_visible_events=partial(
            get_visible_events,
            events=events,
            locations=locations,
            joiners=joiners,
        ),
        get_non_expired_events=partial(
            get_non_expired_events,
            events=events,
            locations=locations,
            joiners=joiners,
        ),
        get_event=partial(
            get_event,
            events=events,
            locations=locations,
            joiners=joiners,
        ),
        cancel_event=partial(
            cancel_event,
            events=events,
            authentication=authentication,
            deletion_delay_minutes=current_settings.canceled_event_deletion_delay_minutes,
            realtime=realtime_publisher,
        ),
        uncancel_event=partial(
            uncancel_event,
            events=events,
            authentication=authentication,
            deletion_delay_minutes=current_settings.event_deletion_delay_minutes,
            deletion_delay_when_no_date_in_minutes=current_settings.event_deletion_delay_when_no_date_in_minutes,
            realtime=realtime_publisher,
        ),
        update_event=partial(
            update_event,
            events=events,
            locations=locations,
            deletion_delay_minutes=current_settings.event_deletion_delay_minutes,
            deletion_delay_when_no_date_in_minutes=current_settings.event_deletion_delay_when_no_date_in_minutes,
            authentication=authentication,
            realtime=realtime_publisher,
        ),
        get_joiners_for_events=partial(
            get_joiners_for_events,
            joiners=joiners,
        ),
        join_event=partial(
            join_event,
            events=events,
            joiners=joiners,
            authentication=authentication,
            realtime=realtime_publisher,
        ),
        leave_event=partial(
            leave_event,
            joiners=joiners,
            authentication=authentication,
            realtime=realtime_publisher,
        ),
        get_all_guests=partial(
            get_all_guests,
            events=events,
            joiners=joiners,
        ),
        delete_expired_events=partial(delete_expired_events, events=events),
        realtime=realtime_publisher,
        database=database,
    )
    logger.info(
        "Application setup completed",
        extra={
            "checkpoint_id": "application-setup-complete",
            "database_dialect": database.engine.dialect.name,
        },
    )
    return application


@lru_cache(maxsize=1)
def get_application() -> Application:
    """Return the process-wide application instance."""
    return build_application()
