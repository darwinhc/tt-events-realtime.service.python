"""FastAPI routes for event joiner operations."""

from fastapi import APIRouter, Depends, Request

from src.domain.dtos import JoinEventRequest
from src.domain.entities import Joiner
from src.entrypoints.fastapi.users.dependencies import user_name_from_token
from src.entrypoints.fastapi.users.openapi import (
    AUTH_ERROR_RESPONSES,
    COMMON_ERROR_RESPONSES,
    CONFLICT_RESPONSE,
    NOT_FOUND_RESPONSE,
)

router = APIRouter(tags=["Joiners"])


@router.post(
    "/joiners",
    status_code=201,
    response_model=Joiner,
    summary="Join an event",
    description="Adds the authenticated user as a joiner of an event.",
    operation_id="joinEvent",
    responses={
        **AUTH_ERROR_RESPONSES,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **COMMON_ERROR_RESPONSES,
    },
)
async def join_event(
        request: Request,
        body: JoinEventRequest,
        user_name: str = Depends(user_name_from_token),
) -> Joiner:
    """Authenticated user joins to active event"""
    return request.app.state.application.join_event(
        user_name=user_name,
        event_id=body.event_id,
    )


@router.get(
    "/events/{event_id}/joiners",
    response_model=list[Joiner],
    summary="List event joiners",
    description="Returns all users who joined the given event.",
    operation_id="listEventJoiners",
    responses={
        **NOT_FOUND_RESPONSE,
        **COMMON_ERROR_RESPONSES,
    },
)
async def get_all_guests(request: Request, event_id: int) -> list[Joiner]:
    """Returns all users who joined the given event."""
    return request.app.state.application.get_all_guests(event_id=event_id)


@router.delete(
    "/joiners/{event_id}",
    response_model=Joiner,
    summary="Leave an event",
    description="Removes the authenticated user from the given event.",
    operation_id="leaveEvent",
    responses={
        **AUTH_ERROR_RESPONSES,
        **NOT_FOUND_RESPONSE,
        **COMMON_ERROR_RESPONSES,
    },
)
async def leave_event(
        request: Request,
        event_id: int,
        user_name: str = Depends(user_name_from_token),
) -> Joiner:
    """Authenticated user leaves an event"""
    return request.app.state.application.leave_event(
        user_name=user_name,
        event_id=event_id,
    )
