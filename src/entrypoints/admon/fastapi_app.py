"""Administrative FastAPI inbound adapter."""

from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text

from src.application import Application, build_application
from src.domain.dtos import EventFilters, EventPage, EventQuery
from src.domain.entities import EventStatus
from src.domain.exceptions import (
    DomainValidationError,
    EntityNotFoundError,
)
from src.infra.config import get_settings


def create_fastapi_app(
    application: Optional[Application] = None,
) -> FastAPI:
    """Create the internal administrative HTTP application."""
    app = FastAPI(
        title="events service administration",
        summary="Internal event querying and administration",
    )
    app.state.application = application or build_application(
        settings=get_settings()
    )

    @app.exception_handler(DomainValidationError)
    async def handle_domain_validation(
        _request: Request,
        error: DomainValidationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(ValidationError)
    async def handle_pydantic_validation(
        _request: Request,
        error: ValidationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": error.errors()})

    @app.exception_handler(EntityNotFoundError)
    async def handle_entity_not_found(
        _request: Request,
        error: EntityNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        with app.state.application.database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/events", response_model=EventPage)
    async def get_non_expired_events(
        status: Optional[list[EventStatus]] = Query(default=None),
        name: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        location_id: Optional[int] = Query(default=None, gt=0),
        deletion_date_from: Optional[datetime] = None,
        deletion_date_to: Optional[datetime] = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=100),
    ) -> EventPage:
        return app.state.application.get_non_expired_events(
            query=EventQuery(
                filters=EventFilters.from_calendar_dates(
                    statuses=status,
                    name=name,
                    from_date=from_date,
                    to_date=to_date,
                    location_id=location_id,
                    deletion_date_from=deletion_date_from,
                    deletion_date_to=deletion_date_to,
                ),
                page=page,
                page_size=page_size,
            )
        )

    return app
