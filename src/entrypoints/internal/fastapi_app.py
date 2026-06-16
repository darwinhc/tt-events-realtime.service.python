"""Administrative FastAPI inbound adapter."""

from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI, Query
from sqlalchemy import text

from src.entrypoints.register_fastapi_exception_handlers import register_fast_api_exception_handlers
from src.application import Application, build_application
from src.domain.dtos import EventFilters, EventPage, EventQuery
from src.domain.entities import EventStatus
from src.infra.config import get_settings


def create_fastapi_app(
    application: Optional[Application] = None,
) -> FastAPI:
    """Create the internal administrative HTTP application."""
    app = FastAPI(
        title="Events service administration",
        summary="Internal event querying and administration",
    )
    app.state.application = application or build_application(
        settings=get_settings()
    )
    register_fast_api_exception_handlers(app)

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
