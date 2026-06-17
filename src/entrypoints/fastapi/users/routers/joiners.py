"""FastAPI routes for event joiner operations."""
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.params import Query

from src.domain.dtos.joiner_info import JoinerInfo
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
    "/joiners",
    response_model=list[JoinerInfo],
    summary="Get active joiners for multiple events",
    description=(
        "Returns active joiners for the provided event ids. "
        "Use repeated query parameters, for example: "
        "`/joiners?event_ids=1&event_ids=2&event_ids=3`."
    ),
    responses={
        **COMMON_ERROR_RESPONSES,
    }
)
async def get_joiners_for_events(
    request: Request,
    event_ids: Annotated[
        list[int],
        Query(
            description="Event ids to retrieve active joiners for.",
            min_length=1,
        ),
    ],
) -> list[JoinerInfo]:
    """Return active joiners for the requested events."""
    unique_event_ids = set(event_ids)

    return request.app.state.application.get_joiners_for_events(
        event_ids=unique_event_ids,
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
