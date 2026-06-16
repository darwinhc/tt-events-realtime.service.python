"""FastAPI routes for event operations."""

from fastapi import APIRouter, Depends, Request

from src.domain.dtos import EventCreate, EventDetails, EventUpdate
from src.domain.entities import Event
from src.entrypoints.fastapi.users.dependencies import user_name_from_token
from src.entrypoints.fastapi.users.openapi import (
    AUTH_ERROR_RESPONSES,
    COMMON_ERROR_RESPONSES,
    CONFLICT_RESPONSE,
    NOT_FOUND_RESPONSE,
)

router = APIRouter(prefix="/events", tags=["Events"])


@router.post(
    "",
    status_code=201,
    response_model=Event,
    summary="Create an event",
    description=(
            "Creates a new event using the authenticated bearer token as the "
            "organizer user name."
    ),
    operation_id="createEvent",
    responses={
        **AUTH_ERROR_RESPONSES,
        **CONFLICT_RESPONSE,
        **COMMON_ERROR_RESPONSES,
    },
)
async def create_event(
        request: Request,
        body: EventCreate,
        user_name: str = Depends(user_name_from_token),
) -> Event:
    return request.app.state.application.create_event_and_resolve_location(
        event=body.to_event(organizer=user_name),
    )


@router.get(
    "",
    response_model=list[EventDetails],
    summary="List visible events",
    description="Returns all events visible according to the domain rules.",
    operation_id="listVisibleEvents",
)
async def get_visible_events(request: Request) -> list[EventDetails]:
    return request.app.state.application.get_visible_events()


@router.get(
    "/{event_id}",
    response_model=EventDetails,
    summary="Get event details",
    description="Returns the details of a single event by its identifier.",
    operation_id="getEventById",
    responses={
        **NOT_FOUND_RESPONSE,
        **COMMON_ERROR_RESPONSES,
    },
)
async def get_event(request: Request, event_id: int) -> EventDetails:
    return request.app.state.application.get_event(event_id=event_id)


@router.patch(
    "/{event_id}",
    response_model=Event,
    summary="Update an event",
    description="Updates an event using partial changes. Only the organizer can update it.",
    operation_id="updateEvent",
    responses={
        **AUTH_ERROR_RESPONSES,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **COMMON_ERROR_RESPONSES,
    },
)
async def update_event(
        request: Request,
        event_id: int,
        changes: EventUpdate,
        user_name: str = Depends(user_name_from_token),
) -> Event:
    return request.app.state.application.update_event(
        event_id=event_id,
        actor_user_name=user_name,
        changes=changes,
    )


@router.post(
    "/{event_id}/cancel",
    response_model=Event,
    summary="Cancel an event",
    description="Cancels an event. Only the organizer can cancel it.",
    operation_id="cancelEvent",
    responses={
        **AUTH_ERROR_RESPONSES,
        **NOT_FOUND_RESPONSE,
        **COMMON_ERROR_RESPONSES,
    },
)
async def cancel_event(
        request: Request,
        event_id: int,
        user_name: str = Depends(user_name_from_token),
) -> Event:
    return request.app.state.application.cancel_event(
        event_id=event_id,
        actor_user_name=user_name,
    )


@router.post(
    "/{event_id}/uncancel",
    response_model=Event,
    summary="Restore a cancelled event",
    description="Restores a previously cancelled event. Only the organizer can restore it.",
    operation_id="uncancelEvent",
    responses={
        **AUTH_ERROR_RESPONSES,
        **NOT_FOUND_RESPONSE,
        **COMMON_ERROR_RESPONSES,
    },
)
async def uncancel_event(
        request: Request,
        event_id: int,
        user_name: str = Depends(user_name_from_token),
) -> Event:
    """Restore a previously cancelled event."""
    return request.app.state.application.uncancel_event(
        event_id=event_id,
        actor_user_name=user_name,
    )
