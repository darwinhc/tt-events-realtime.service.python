"""FastAPI inbound adapter."""

import logging
import time
from typing import Optional
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from sqlalchemy import text

from src.application import Application, build_application
from src.domain.dtos import (
    EventCreate,
    EventDetails,
    EventUpdate,
    JoinEventRequest,
    LocationUpdate,
)
from src.domain.entities import Event, Joiner, Location
from src.domain.exceptions import (
    AuthorizationError,
    DomainValidationError,
    EntityConflictError,
    EntityNotFoundError,
)
from src.infra.events.fastapi_websocket import FastAPIWebSocketPublisher
from src.infra.config import get_settings
from src.infra.logging import reset_transaction_id, set_transaction_id


logger = logging.getLogger(__name__)
_bearer_scheme = HTTPBearer(auto_error=False)


def _user_name_from_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        _bearer_scheme
    ),
) -> str:
    """Return the visible user encoded as the bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authorization bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_name = credentials.credentials.strip()
    if not user_name or len(user_name) > 64:
        raise HTTPException(
            status_code=401,
            detail="Authorization bearer token is invalid.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_name


def create_fastapi_app(
    application: Optional[Application] = None,
    realtime: Optional[FastAPIWebSocketPublisher] = None,
    cors_allowed_origins: Optional[tuple[str, ...]] = None,
) -> FastAPI:
    """Create the HTTP adapter around an already composed application."""
    runtime_settings = get_settings() if application is None else None
    realtime_publisher = realtime
    if realtime_publisher is None and application is not None:
        configured_publisher = application.realtime
        if isinstance(configured_publisher, FastAPIWebSocketPublisher):
            realtime_publisher = configured_publisher
    realtime_publisher = realtime_publisher or FastAPIWebSocketPublisher()

    app = FastAPI(
        title="events service",
        summary="Receives and stores events, organizers, and flexible locations",
    )
    app.state.application = application or build_application(
        settings=runtime_settings,
        realtime=realtime_publisher,
    )
    app.state.realtime = realtime_publisher
    configured_origins = cors_allowed_origins
    if configured_origins is None and runtime_settings is not None:
        configured_origins = runtime_settings.cors_allowed_origins
    if configured_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(configured_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def log_http_request(request: Request, call_next):
        transaction_id = request.headers.get("x-transaction-id") or str(
            uuid4()
        )
        token = set_transaction_id(transaction_id)
        started_at = time.perf_counter()
        client_host = request.client.host if request.client else None
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "HTTP request failed",
                extra={
                    "transaction_id": transaction_id,
                    "checkpoint_id": "http-request-failed",
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "client_ip": client_host,
                    "duration_ms": round(
                        (time.perf_counter() - started_at) * 1000,
                        2,
                    ),
                },
            )
            raise
        else:
            route = request.scope.get("route")
            route_path = getattr(route, "path", request.url.path)
            response.headers["X-Transaction-ID"] = transaction_id
            logger.info(
                "HTTP request completed",
                extra={
                    "transaction_id": transaction_id,
                    "checkpoint_id": "http-request-completed",
                    "http_method": request.method,
                    "http_route": route_path,
                    "http_path": request.url.path,
                    "http_status": response.status_code,
                    "client_ip": client_host,
                    "duration_ms": round(
                        (time.perf_counter() - started_at) * 1000,
                        2,
                    ),
                },
            )
            return response
        finally:
            reset_transaction_id(token)

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

    @app.exception_handler(EntityConflictError)
    async def handle_entity_conflict(
        _request: Request,
        error: EntityConflictError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(AuthorizationError)
    async def handle_authorization_error(
        _request: Request,
        error: AuthorizationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        with app.state.application.database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.post("/events", status_code=201, response_model=Event)
    async def create_event(
        request: EventCreate,
        user_name: str = Depends(_user_name_from_token),
    ) -> Event:
        return app.state.application.create_event_and_resolve_location(
            event=request.to_event(organizer=user_name),
        )

    @app.get("/events", response_model=list[EventDetails])
    async def get_visible_events() -> list[EventDetails]:
        return app.state.application.get_visible_events()

    @app.get("/events/{event_id}", response_model=EventDetails)
    async def get_event(event_id: int) -> EventDetails:
        return app.state.application.get_event(event_id=event_id)

    @app.get("/locations", response_model=list[Location])
    async def get_locations() -> list[Location]:
        return app.state.application.get_locations()

    @app.patch("/locations/{location_id}", response_model=Location)
    async def update_location(
        location_id: int,
        changes: LocationUpdate,
    ) -> Location:
        return app.state.application.update_location(
            location_id=location_id,
            changes=changes,
        )

    @app.patch("/events/{event_id}", response_model=Event)
    async def update_event(
        event_id: int,
        changes: EventUpdate,
        user_name: str = Depends(_user_name_from_token),
    ) -> Event:
        return app.state.application.update_event(
            event_id=event_id,
            actor_user_name=user_name,
            changes=changes,
        )

    @app.post("/events/{event_id}/cancel", response_model=Event)
    async def cancel_event(
        event_id: int,
        user_name: str = Depends(_user_name_from_token),
    ) -> Event:
        return app.state.application.cancel_event(
            event_id=event_id,
            actor_user_name=user_name,
        )

    @app.post("/events/{event_id}/uncancel", response_model=Event)
    async def uncancel_event(
        event_id: int,
        user_name: str = Depends(_user_name_from_token),
    ) -> Event:
        return app.state.application.uncancel_event(
            event_id=event_id,
            actor_user_name=user_name,
        )

    @app.post("/joiners", status_code=201, response_model=Joiner)
    async def join_event(
        request: JoinEventRequest,
        user_name: str = Depends(_user_name_from_token),
    ) -> Joiner:
        return app.state.application.join_event(
            user_name=user_name,
            event_id=request.event_id,
        )

    @app.get("/events/{event_id}/joiners", response_model=list[Joiner])
    async def get_all_guests(event_id: int) -> list[Joiner]:
        return app.state.application.get_all_guests(event_id=event_id)

    @app.delete(
        "/joiners/{event_id}",
        response_model=Joiner,
    )
    async def leave_event(
        event_id: int,
        user_name: str = Depends(_user_name_from_token),
    ) -> Joiner:
        return app.state.application.leave_event(
            user_name=user_name,
            event_id=event_id,
        )

    @app.websocket("/ws/events")
    async def all_events_websocket(websocket: WebSocket) -> None:
        await _serve_websocket(websocket)

    async def _serve_websocket(websocket: WebSocket) -> None:
        transaction_id = websocket.headers.get("x-transaction-id") or str(
            uuid4()
        )
        token = set_transaction_id(transaction_id)
        started_at = time.perf_counter()
        client_host = websocket.client.host if websocket.client else None
        subscription = "all-events"
        try:
            await app.state.realtime.connect(websocket)
            logger.info(
                "WebSocket connection established",
                extra={
                    "transaction_id": transaction_id,
                    "checkpoint_id": "websocket-connected",
                    "websocket_route": websocket.url.path,
                    "subscription": subscription,
                    "client_ip": client_host,
                    "active_connections": (
                        app.state.realtime.connection_count
                    ),
                },
            )
            while True:
                message = await websocket.receive_json()
                if message.get("action") == "ping":
                    await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect as error:
            logger.info(
                "WebSocket client disconnected",
                extra={
                    "transaction_id": transaction_id,
                    "checkpoint_id": "websocket-disconnected",
                    "websocket_route": websocket.url.path,
                    "subscription": subscription,
                    "client_ip": client_host,
                    "close_code": error.code,
                    "duration_ms": round(
                        (time.perf_counter() - started_at) * 1000,
                        2,
                    ),
                },
            )
        except Exception:
            logger.exception(
                "WebSocket connection failed",
                extra={
                    "transaction_id": transaction_id,
                    "checkpoint_id": "websocket-failed",
                    "websocket_route": websocket.url.path,
                    "subscription": subscription,
                    "client_ip": client_host,
                },
            )
            raise
        finally:
            await app.state.realtime.disconnect(websocket)
            reset_transaction_id(token)

    return app
