"""Update-event use case."""

from src.domain.use_cases.events.verify_event_dates import verify_event_dates_consistency
from src.domain.dtos import EventUpdate
from src.domain.entities import Event, EventStatus, RealtimeEvent
from src.domain.exceptions import (
    AuthorizationError,
    DomainValidationError,
    EntityNotFoundError,
)
from src.domain.ports.database import EventsRepository, LocationsRepository
from src.domain.ports.authentication import AuthenticationPort
from src.domain.ports.events import (
    NullRealtimeEventPublisher,
    RealtimeEventPublisher,
)


def update_event(
    event_id: int,
    actor_user_name: str,
    changes: EventUpdate,
    events: EventsRepository,
    locations: LocationsRepository,
    deletion_delay_minutes: int,
    deletion_delay_when_no_date_in_minutes: int,
    authentication: AuthenticationPort,
    realtime: RealtimeEventPublisher = NullRealtimeEventPublisher(),
) -> Event:
    """Update an active event when the actor is its organizer."""
    event = events.get_by_id(event_id)
    if event is None:
        raise EntityNotFoundError(f"Event '{event_id}' does not exist.")
    actor = authentication.authenticate(actor_user_name)
    if actor.id != event.organizer_id:
        raise AuthorizationError(
            "Only the event organizer can update this event."
        )
    if event.status is EventStatus.CANCELED:
        raise DomainValidationError("A canceled event cannot be updated.")

    update_values = changes.model_dump(
        exclude_unset=True,
        exclude_none=False,
    )
    location_id = update_values.get("location_id")
    if (
        location_id is not None
        and locations.get_by_id(location_id) is None
    ):
        raise EntityNotFoundError(
            f"Location '{location_id}' does not exist."
        )

    updated_event = Event.model_validate(
        {
            **event.model_dump(exclude={"location"}),
            **update_values,
        }
    ).schedule_deletion_after_event(deletion_delay_minutes, deletion_delay_when_no_date_in_minutes)

    verify_event_dates_consistency(updated_event)

    persisted_event = events.update(updated_event)
    realtime.publish(
        RealtimeEvent(
            type="event.updated",
            event_id=persisted_event.id,
            payload=persisted_event.model_dump(mode="json"),
        )
    )
    return persisted_event
