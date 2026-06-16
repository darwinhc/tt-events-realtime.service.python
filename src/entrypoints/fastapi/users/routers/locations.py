"""FastAPI routes for location operations."""

from fastapi import APIRouter, Request

from src.domain.dtos import LocationUpdate
from src.domain.entities import Location
from src.entrypoints.fastapi.users.openapi import COMMON_ERROR_RESPONSES, NOT_FOUND_RESPONSE

router = APIRouter(prefix="/locations", tags=["Locations"])


@router.get(
    "",
    response_model=list[Location],
    summary="List locations",
    description="Returns all available event locations.",
    operation_id="listLocations",
)
async def get_locations(request: Request) -> list[Location]:
    """Returns all available event locations."""
    return request.app.state.application.get_locations()


@router.patch(
    "/{location_id}",
    response_model=Location,
    summary="Update a location",
    description="Updates an existing location using partial changes.",
    operation_id="updateLocation",
    responses={
        **NOT_FOUND_RESPONSE,
        **COMMON_ERROR_RESPONSES,
    },
)
async def update_location(
        request: Request,
        location_id: int,
        changes: LocationUpdate,
) -> Location:
    """Updates an existing location using partial changes."""
    return request.app.state.application.update_location(
        location_id=location_id,
        changes=changes,
    )
