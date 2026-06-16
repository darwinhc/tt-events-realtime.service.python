"""FastAPI inbound adapter."""

import logging
import time
from typing import Optional
from uuid import uuid4

from fastapi import (
    FastAPI,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from sqlalchemy import text

from src.application import Application, build_application
from src.entrypoints.register_fastapi_exception_handlers import register_fast_api_exception_handlers
from src.entrypoints.users.openapi import OPENAPI_TAGS
from src.entrypoints.users.routers import events_router, locations_router, joiners_router
from src.infra.config import get_settings
from src.infra.events.fastapi_websocket import FastAPIWebSocketPublisher
from src.infra.logging import reset_transaction_id, set_transaction_id

logger = logging.getLogger(__name__)
_bearer_scheme = HTTPBearer(auto_error=False)


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
        title="Events Service",
        summary="Receives and stores events, organizers, joiners, and flexible locations.",
        description=(
            "Events Service exposes HTTP and WebSocket APIs to manage events, "
            "locations, attendance, and realtime updates."
        ),
        version="1.0.0",
        openapi_tags=OPENAPI_TAGS,
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

    register_fast_api_exception_handlers(app)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        with app.state.application.database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    app.include_router(events_router)
    app.include_router(locations_router)
    app.include_router(joiners_router)

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
