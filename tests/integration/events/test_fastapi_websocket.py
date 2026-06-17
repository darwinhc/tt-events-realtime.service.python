"""Full FastAPI HTTP and WebSocket integration tests."""

import asyncio
import logging
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from time import sleep
from types import SimpleNamespace
from typing import Callable, Optional

import pytest
from alembic import command
from alembic.config import Config
from fastapi import WebSocket
from fastapi.testclient import TestClient

from src.application import build_application
from src.entrypoints.fastapi.users import create_fastapi_app
from src.infra.config import Settings
from src.infra.events.fastapi_websocket import FastAPIWebSocketPublisher


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class PausedConnectionPublisher(FastAPIWebSocketPublisher):
    """Pause a handshake before the connection can receive notifications."""

    def __init__(self) -> None:
        super().__init__()
        self.connect_started = threading.Event()
        self.allow_connection = threading.Event()
        self.connected = threading.Event()

    async def connect(
        self,
        websocket: WebSocket,
    ) -> None:
        self.connect_started.set()
        await asyncio.to_thread(self.allow_connection.wait)
        await super().connect(websocket)
        self.connected.set()


@pytest.fixture
def database_url(tmp_path) -> str:
    """Return an isolated SQLite database URL for a test."""
    return f"sqlite:///{tmp_path / 'events.db'}"


@pytest.fixture
def run_migrations() -> Callable[[str], None]:
    """Return a helper that applies Alembic migrations to a database."""

    def _run_migrations(database_url: str) -> None:
        alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
        alembic_cfg.cmd_opts = SimpleNamespace(
            x=[f"database_url={database_url}"],
        )
        command.upgrade(alembic_cfg, "head")
        logging.getLogger(
            "src.entrypoints.fastapi.users.fastapi_app"
        ).disabled = False

    return _run_migrations


@pytest.fixture
def settings(database_url: str) -> Settings:
    """Return test settings bound to the isolated test database."""
    return Settings(
        app_name="events-service",
        environment="test",
        database_url=database_url,
        sqlalchemy_echo=False,
        log_level="ERROR",
    )


@pytest.fixture
def realtime_publisher() -> FastAPIWebSocketPublisher:
    """Return the default realtime publisher used by the FastAPI app."""
    return FastAPIWebSocketPublisher()


@pytest.fixture
def paused_realtime_publisher() -> PausedConnectionPublisher:
    """Return a realtime publisher that can pause WebSocket connection setup."""
    return PausedConnectionPublisher()


@pytest.fixture
def application(
    database_url: str,
    settings: Settings,
    realtime_publisher: FastAPIWebSocketPublisher,
    run_migrations: Callable[[str], None],
):
    """Build the application after applying database migrations."""
    run_migrations(database_url)

    return build_application(
        settings,
        realtime=realtime_publisher,
    )


@pytest.fixture
def client(
    application,
    realtime_publisher: FastAPIWebSocketPublisher,
):
    """Return a TestClient for the user-facing FastAPI app."""
    with TestClient(
        create_fastapi_app(application, realtime=realtime_publisher)
    ) as test_client:
        yield test_client


@pytest.fixture
def build_client(
    database_url: str,
    settings: Settings,
    run_migrations: Callable[[str], None],
) -> Callable[[Optional[FastAPIWebSocketPublisher]], TestClient]:
    """Return a factory for building clients with a custom publisher."""

    def _build_client(
        realtime: Optional[FastAPIWebSocketPublisher] = None,
    ) -> TestClient:
        publisher = realtime or FastAPIWebSocketPublisher()

        run_migrations(database_url)

        application = build_application(
            settings,
            realtime=publisher,
        )

        return TestClient(
            create_fastapi_app(application, realtime=publisher)
        )

    return _build_client


@pytest.fixture
def create_event() -> Callable[[TestClient, str], dict]:
    """Return a helper that creates an event through the HTTP API."""

    def _create_event(
        client: TestClient,
        title: str = "Realtime event",
    ) -> dict:
        event_response = client.post(
            "/events",
            headers={"Authorization": "Bearer organizer"},
            json={
                "title": title,
                "duration_in_minutes": 60,
                "location": {"address": f"{title} location"},
            },
        )

        assert event_response.status_code == 201
        return event_response.json()

    return _create_event


@pytest.fixture
def join_event():
    """Return a helper that joins a user to an event through the HTTP API."""

    def _join_event(
        client: TestClient,
        event_id: int,
        user_name: str,
    ):
        return client.post(
            "/joiners",
            headers={"Authorization": f"Bearer {user_name}"},
            json={"event_id": event_id},
        )

    return _join_event


def test_broadcasts_the_complete_happy_path_to_every_connected_user(
    client,
    join_event,
    create_event,
) -> None:
    event = create_event(client, "happy path")
    with (
        client.websocket_connect("/ws/events") as first_user,
        client.websocket_connect("/ws/events") as second_user,
    ):
        join_response = join_event(client, event["id"], "guest")
        first_joined = first_user.receive_json()
        second_joined = second_user.receive_json()

        leave_response = client.delete(
            f"/joiners/{event['id']}",
            headers={"Authorization": "Bearer guest"},
        )
        first_left = first_user.receive_json()
        second_left = second_user.receive_json()

        cancel_response = client.post(
            f"/events/{event['id']}/cancel",
            headers={"Authorization": "Bearer organizer"},
        )
        first_canceled = first_user.receive_json()
        second_canceled = second_user.receive_json()

    assert join_response.status_code == 201
    assert leave_response.status_code == 200
    assert cancel_response.status_code == 200
    assert first_joined == second_joined
    assert first_left == second_left
    assert first_canceled == second_canceled
    assert [
        first_joined["type"],
        first_left["type"],
        first_canceled["type"],
    ] == ["joiner.joined", "joiner.left", "event.canceled"]
    assert first_joined["payload"] == {
        "joiner": {
            "id": first_joined["payload"]["joiner"]["id"],
            "user_id": first_joined["payload"]["joiner"]["user_id"],
            "user_name": "guest",
            "event_id": event["id"],
            "joined_at": first_joined["payload"]["joiner"]["joined_at"],
            "left_at": None,
        },
        "joiners_count": 1,
    }
    assert first_left["payload"]["joiners_count"] == 0
    assert first_left["payload"]["joiner"]["id"] == (
        first_joined["payload"]["joiner"]["id"]
    )
    assert first_left["payload"]["joiner"]["left_at"] is not None


def test_client_reconciles_by_api_when_join_happens_during_ws_connection(
    build_client,
    paused_realtime_publisher,
    create_event,
    join_event,
) -> None:
    http_client = build_client(paused_realtime_publisher)
    websocket_client = TestClient(http_client.app)
    event = create_event(http_client, "realtime event")
    received: dict = {}

    def connect_and_receive_next_change() -> None:
        with websocket_client.websocket_connect("/ws/events") as websocket:
            received.update(websocket.receive_json())

    connection_thread = threading.Thread(
        target=connect_and_receive_next_change,
        daemon=True,
    )
    connection_thread.start()
    assert paused_realtime_publisher.connect_started.wait(timeout=2)

    missed_join = join_event(
        http_client,
        event["id"],
        "joined-during-connect",
    )
    assert missed_join.status_code == 201

    paused_realtime_publisher.allow_connection.set()
    assert paused_realtime_publisher.connected.wait(timeout=2)

    visible_join = join_event(
        http_client,
        event["id"],
        "joined-after-connect",
    )
    assert visible_join.status_code == 201
    connection_thread.join(timeout=2)
    assert not connection_thread.is_alive()

    current_event = http_client.get(f"/events/{event['id']}")
    current_joiners = http_client.get(
        f"/events/{event['id']}/joiners"
    )

    assert received["payload"]["joiner"]["user_name"] == (
        "joined-after-connect"
    )
    assert received["payload"]["joiners_count"] == 2
    assert current_event.json()["joiners_count"] == 2
    assert [
        joiner["user_name"] for joiner in current_joiners.json()
    ] == ["joined-after-connect", "joined-during-connect"]
    assert all(
        joiner["id"] is not None and joiner["left_at"] is None
        for joiner in current_joiners.json()
    )


def test_reconnected_client_recovers_offline_changes_from_api(
    client,
    create_event,
    join_event,
) -> None:
    event = create_event(client)

    with client.websocket_connect("/ws/events") as websocket:
        join_event(client, event["id"], "first")
        assert websocket.receive_json()["payload"]["joiners_count"] == 1

    offline_join = join_event(client, event["id"], "offline")
    assert offline_join.status_code == 201

    with client.websocket_connect("/ws/events") as websocket:
        join_event(client, event["id"], "after-reconnect")
        after_reconnect = websocket.receive_json()

    authoritative_event = client.get(f"/events/{event['id']}")
    authoritative_joiners = client.get(
        f"/events/{event['id']}/joiners"
    )

    assert after_reconnect["payload"]["joiners_count"] == 3
    assert authoritative_event.json()["joiners_count"] == 3
    assert {
        joiner["user_name"] for joiner in authoritative_joiners.json()
    } == {
        "first",
        "offline",
        "after-reconnect",
    }


def test_rejected_duplicate_join_does_not_emit_a_false_notification(
    client,
    create_event,
    join_event,
) -> None:
    event = create_event(client)

    with client.websocket_connect("/ws/events") as websocket:
        assert join_event(client, event["id"], "guest").status_code == 201
        first_join = websocket.receive_json()

        duplicate = join_event(client, event["id"], "guest")
        assert duplicate.status_code == 409

        assert join_event(client, event["id"], "other").status_code == 201
        next_notification = websocket.receive_json()

    assert first_join["payload"]["joiners_count"] == 1
    assert next_notification["payload"] == {
        "joiner": {
            "id": next_notification["payload"]["joiner"]["id"],
            "user_id": next_notification["payload"]["joiner"]["user_id"],
            "user_name": "other",
            "event_id": event["id"],
            "joined_at": next_notification["payload"]["joiner"]["joined_at"],
            "left_at": None,
        },
        "joiners_count": 2,
    }


def test_websocket_ping_keeps_the_connection_usable(
    client,
    create_event,
    join_event,
) -> None:
    event = create_event(client)

    with client.websocket_connect("/ws/events") as websocket:
        websocket.send_json({"action": "ping"})
        assert websocket.receive_json() == {"type": "pong"}

        join_event(client, event["id"], "guest")
        notification = websocket.receive_json()

    assert notification["type"] == "joiner.joined"
    assert notification["event_id"] == event["id"]


def test_event_update_is_broadcast_to_connected_users(
    client,
    create_event,
) -> None:
    event = create_event(client)

    with client.websocket_connect("/ws/events") as global_user:
        response = client.patch(
            f"/events/{event['id']}",
            headers={"Authorization": "Bearer organizer"},
            json={"title": "Updated in realtime"},
        )
        global_message = global_user.receive_json()

    assert response.status_code == 200
    assert global_message["type"] == "event.updated"
    assert global_message["payload"]["title"] == "Updated in realtime"


def test_location_update_is_broadcast_with_persisted_payload(
    client,
    create_event,
) -> None:
    event = create_event(client)

    with client.websocket_connect("/ws/events") as websocket:
        response = client.patch(
            f"/locations/{event['location_id']}",
            json={"name": "Updated location in realtime"},
        )
        notification = websocket.receive_json()

    assert response.status_code == 200
    assert notification["type"] == "location.updated"
    assert notification["event_id"] is None
    assert notification["location_id"] == event["location_id"]
    assert notification["payload"] == response.json()
    assert client.get(f"/events/{event['id']}").json()["location"] == (
        response.json()
    )


def test_completed_join_does_not_emit_a_notification(
    client,
    create_event,
    join_event,
) -> None:
    completed = client.post(
        "/events",
        headers={"Authorization": "Bearer organizer"},
        json={
            "title": "Completed realtime event",
            "scheduled_at": (datetime.now(timezone.utc) - timedelta(minutes=59.99)).isoformat(),
            "duration_in_minutes": 60,
            "location": {"address": "Past"},
        },
    ).json()
    future = create_event(client, "Future signal")

    sleep(2)
    with client.websocket_connect("/ws/events") as websocket:
        rejected = join_event(client, completed["id"], "guest")
        accepted = join_event(client, future["id"], "other")
        notification = websocket.receive_json()

    assert rejected.status_code == 422
    assert accepted.status_code == 201
    assert notification["type"] == "joiner.joined"
    assert notification["event_id"] == future["id"]


def test_websocket_logging_describes_connection_and_disconnection(
    client,
    create_event,
    caplog,
) -> None:
    create_event(client)

    with caplog.at_level(
        logging.INFO,
        logger="src.entrypoints.fastapi.users.fastapi_app",
    ):
        with client.websocket_connect(
            "/ws/events",
            headers={"X-Transaction-ID": "websocket-session-123"},
        ) as websocket:
            websocket.send_json({"action": "ping"})
            assert websocket.receive_json() == {"type": "pong"}

    connected = next(
        record
        for record in caplog.records
        if getattr(record, "checkpoint_id", None) == "websocket-connected"
    )
    disconnected = next(
        record
        for record in caplog.records
        if getattr(record, "checkpoint_id", None)
        == "websocket-disconnected"
    )
    assert connected.transaction_id == "websocket-session-123"
    assert connected.websocket_route == "/ws/events"
    assert connected.subscription == "all-events"
    assert connected.active_connections == 1
    assert disconnected.transaction_id == "websocket-session-123"
    assert disconnected.close_code == 1000
    assert disconnected.duration_ms >= 0