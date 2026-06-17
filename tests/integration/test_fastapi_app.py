"""FastAPI inbound-adapter integration tests."""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from time import sleep

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from src.application import build_application
from src.domain.dtos import EventFilters, EventQuery
from src.domain.entities import Location
from src.entrypoints.fastapi.users import create_fastapi_app
from src.infra.config import Settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANCELED_EVENT_DELETION_DELAY_MINUTES = 20
EVENT_DELETION_DELAY_MINUTES = 40
LOCATION_UNUSED_DELETION_DELAY_MINUTES = 60
EVENT_DELETION_DELAY_WHEN_NO_DATE_IN_MINUTES = 80


def run_migrations(database_url: str) -> None:
    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.cmd_opts = type(
        "CommandOptions",
        (),
        {"x": [f"database_url={database_url}"]},
    )()
    command.upgrade(alembic_cfg, "head")


def build_test_settings(database_url: str) -> Settings:
    return Settings(
        app_name="events-service",
        environment="test",
        database_url=database_url,
        sqlalchemy_echo=False,
        log_level="ERROR",
        canceled_event_deletion_delay_minutes = CANCELED_EVENT_DELETION_DELAY_MINUTES,
        event_deletion_delay_minutes = EVENT_DELETION_DELAY_MINUTES,
        location_unused_deletion_delay_minutes = LOCATION_UNUSED_DELETION_DELAY_MINUTES,
        event_deletion_delay_when_no_date_in_minutes = EVENT_DELETION_DELAY_WHEN_NO_DATE_IN_MINUTES,
    )

@pytest.fixture
def application(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'events.db'}"
    run_migrations(database_url)
    settings = build_test_settings(database_url)

    application = build_application(
        settings
    )
    return application

@pytest.fixture
def client(application):
    return TestClient(create_fastapi_app(application))


def test_creates_event_with_internal_identity_and_embedded_location(
    client, application
) -> None:
    now = datetime.now(timezone.utc)
    duration = 105
    event_response = client.post(
        "/events",
        headers={"Authorization": "Bearer darwin"},
        json={
            "title": "Realtime Systems Meetup",
            "scheduled_at": None,
            "duration_in_minutes": duration,
            "location": {
                "name": "Main Hall",
                "coordinates": {
                    "latitude": 52.5219,
                    "longitude": 13.4132,
                },
            },
        },
    )

    assert event_response.status_code == 201
    assert event_response.json()["scheduled_at"] is None
    assert event_response.json()["duration_in_minutes"] == duration
    assert event_response.json()["organizer"] == "darwin"
    assert event_response.json()["status"] == "active"
    assert event_response.json()["canceled_at"] is None
    assert event_response.json()["deletion_scheduled_at"] is not None

    deletion_scheduled_at = datetime.fromisoformat(event_response.json()["deletion_scheduled_at"]).replace(microsecond=0)
    expected_scheduled_at = (now + timedelta(minutes=EVENT_DELETION_DELAY_WHEN_NO_DATE_IN_MINUTES)).replace(microsecond=0)

    assert  deletion_scheduled_at - expected_scheduled_at < timedelta(seconds=5)

    cancel_response = client.post(
        f"/events/{event_response.json()['id']}/cancel",
        headers={"Authorization": "Bearer darwin"},
    )

    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "canceled"
    assert cancel_response.json()["canceled_at"] is not None
    assert cancel_response.json()["deletion_scheduled_at"] is not None

    forbidden_uncancel = client.post(
        f"/events/{event_response.json()['id']}/uncancel",
        headers={"Authorization": "Bearer another-user"},
    )
    uncancel_response = client.post(
        f"/events/{event_response.json()['id']}/uncancel",
        headers={"Authorization": "Bearer darwin"},
    )

    assert forbidden_uncancel.status_code == 403
    assert uncancel_response.status_code == 200
    assert uncancel_response.json()["status"] == "active"
    assert uncancel_response.json()["canceled_at"] is None
    assert uncancel_response.json()["deletion_scheduled_at"] is not None

    filtered_events = application.get_events(
        query=EventQuery(
            filters=EventFilters(
                statuses=("active",),
                name="systems",
                location_id=event_response.json()["location_id"],
            )
        )
    )

    assert [event.id for event in filtered_events.items] == [
        event_response.json()["id"]
    ]
    assert filtered_events.total == 1
    assert filtered_events.items[0].joiners_count == 0
    assert filtered_events.items[0].location.name == "Main Hall"


def test_health_check_confirms_database_connectivity(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_authentication_is_internal_and_not_exposed(client) -> None:
    response = client.post(
        "/users/authenticate",
        json={"user_name": "darwin"},
    )
    schema = client.get("/openapi.json").json()

    assert response.status_code == 404
    assert "/users/authenticate" not in schema["paths"]
    assert "/locations" in schema["paths"]
    assert "/locations/{location_id}" in schema["paths"]
    assert "/events/{event_id}/joiners/count" not in schema["paths"]
    assert "/ws/events/{event_id}" not in {
        route.path
        for route in client.app.routes
        if hasattr(route, "path")
    }
    assert "/events/resolve-location" not in schema["paths"]
    assert "/events/active/expired" not in schema["paths"]
    assert "/internal/events" not in schema["paths"]


def test_event_creation_requires_a_bearer_user_token(client) -> None:
    payload = {
        "title": "Protected event",
        "duration_in_minutes": 60,
        "location": {"address": "Remote"},
    }

    missing_token = client.post("/events", json=payload)
    wrong_scheme = client.post(
        "/events",
        headers={"Authorization": "Basic ZGFyd2lu"},
        json=payload,
    )

    assert missing_token.status_code == 401
    assert missing_token.headers["www-authenticate"] == "Bearer"
    assert wrong_scheme.status_code == 401


def test_event_api_rejects_legacy_hour_duration_field(client) -> None:
    response = client.post(
        "/events",
        headers={"Authorization": "Bearer darwin"},
        json={
            "title": "Legacy request",
            "duration_in_hours": 1.5,
            "location": {"address": "Remote"},
        },
    )

    assert response.status_code == 422


def test_creates_event_and_resolves_embedded_location(client) -> None:
    now = datetime.now(timezone.utc)
    duration = 90
    response = client.post(
        "/events",
        headers={"Authorization": "Bearer darwin"},
        json={
            "title": "Event with embedded location",
            "scheduled_at": (now + timedelta(hours=1)).isoformat(),
            "duration_in_minutes": duration,
            "location": {
                "name": "Main Hall",
                "address": "Alexanderplatz 1, Berlin",
                "country": "de",
                "city": "BÉRLIN",
                "postal_code": "10178",
                "coordinates": {
                    "latitude": 52.5219,
                    "longitude": 13.4132,
                },
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["location_id"] == 1
    assert response.json()["status"] == "active"
    assert datetime.fromisoformat(response.json()["deletion_scheduled_at"]) == (
        (now + timedelta(hours=1, minutes=duration+EVENT_DELETION_DELAY_MINUTES))
    )
    event_details = client.get(f"/events/{response.json()['id']}").json()
    assert event_details["location"]["country"] == "DE"
    assert event_details["location"]["city"] == "berlin"
    assert event_details["location"]["postal_code"] == "10178"


def test_lists_and_updates_locations_used_by_events(client) -> None:
    event = client.post(
        "/events",
        headers={"Authorization": "Bearer darwin"},
        json={
            "title": "Location update event",
            "duration_in_minutes": 60,
            "location": {
                "name": "Original Hall",
                "address": "Old address",
                "country": "DE",
                "city": "Berlin",
            },
        },
    ).json()

    listed_before = client.get("/locations")
    updated = client.patch(
        f"/locations/{event['location_id']}",
        json={
            "name": "Updated Hall",
            "address": "New address",
            "city": "München",
        },
    )
    listed_after = client.get("/locations")
    event_after = client.get(f"/events/{event['id']}")

    assert listed_before.status_code == 200
    assert listed_before.json()[0]["name"] == "Original Hall"
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Hall"
    assert updated.json()["address"] == "New address"
    assert updated.json()["city"] == "munchen"
    assert listed_after.json() == [updated.json()]
    assert event_after.json()["location"] == updated.json()


def test_location_update_rejects_missing_or_invalid_location(client) -> None:
    missing = client.patch("/locations/999", json={"name": "Missing"})
    empty = client.patch("/locations/999", json={})

    assert missing.status_code == 404
    assert empty.status_code == 422


def test_join_rejects_completed_event_and_accepts_future_event(client) -> None:
    completed = client.post(
        "/events",
        headers={"Authorization": "Bearer organizer"},
        json={
            "title": "Completed event",
            "scheduled_at": (datetime.now(timezone.utc) - timedelta(minutes=59.99)).isoformat(),
            "duration_in_minutes": 60,
            "location": {"address": "Past location"},
        },
    ).json()

    future = client.post(
        "/events",
        headers={"Authorization": "Bearer organizer"},
        json={
            "title": "Future event",
            "scheduled_at": "2099-01-01T10:00:00Z",
            "duration_in_minutes": 60,
            "location": {"address": "Future location"},
        },
    ).json()
    sleep(1)
    rejected = client.post(
        "/joiners",
        headers={"Authorization": "Bearer guest"},
        json={"event_id": completed["id"]},
    )
    accepted = client.post(
        "/joiners",
        headers={"Authorization": "Bearer guest"},
        json={"event_id": future["id"]},
    )

    assert rejected.status_code == 422
    assert rejected.json() == {
        "detail": "A completed event cannot be joined."
    }
    assert client.get(f"/events/{completed['id']}").json()["joiners_count"] == 0
    assert accepted.status_code == 201
    assert client.get(f"/events/{future['id']}").json()["joiners_count"] == 1


def test_internal_use_case_lists_expired_active_events(client) -> None:
    expired_response = client.post(
        "/events",
        headers={"Authorization": "Bearer darwin"},
        json={
            "title": "Expired active event",
            "scheduled_at": "2020-01-01T10:00:00Z",
            "duration_in_minutes": 60,
            "location": {"address": "Remote"},
        },
    )
    assert expired_response.status_code == 422
    assert expired_response.json().get("detail") == 'Event must have a scheduled date in the future.'


def test_joins_and_leaves_event(client) -> None:
    event = client.post(
        "/events",
        headers={"Authorization": "Bearer darwin"},
        json={
            "title": "Joinable event",
            "duration_in_minutes": 60,
            "location": {"address": "Remote"},
        },
    ).json()

    join_response = client.post(
        "/joiners",
        headers={"Authorization": "Bearer external-user"},
        json={"event_id": event["id"]},
    )
    duplicate_response = client.post(
        "/joiners",
        headers={"Authorization": "Bearer external-user"},
        json={"event_id": event["id"]},
    )
    second_join_response = client.post(
        "/joiners",
        headers={"Authorization": "Bearer another-user"},
        json={"event_id": event["id"]},
    )
    list_response = client.get(f"/events/{event['id']}/joiners")
    details_response = client.get(f"/events/{event['id']}")
    leave_response = client.delete(
        f"/joiners/{event['id']}",
        headers={"Authorization": "Bearer external-user"},
    )

    assert join_response.status_code == 201
    assert isinstance(join_response.json()["id"], int)
    assert isinstance(join_response.json()["user_id"], int)
    assert join_response.json()["user_name"] == "external-user"
    assert join_response.json()["event_id"] == event["id"]
    assert join_response.json()["left_at"] is None
    assert duplicate_response.status_code == 409
    assert second_join_response.status_code == 201
    assert list_response.status_code == 200
    assert list_response.json() == [
        second_join_response.json(),
        join_response.json(),
    ]
    assert details_response.status_code == 200
    assert details_response.json()["joiners_count"] == 2
    assert leave_response.status_code == 200
    assert leave_response.json()["id"] == join_response.json()["id"]
    assert leave_response.json()["left_at"] is not None

    active_after_leave = client.get(f"/events/{event['id']}/joiners")
    rejoin_response = client.post(
        "/joiners",
        headers={"Authorization": "Bearer external-user"},
        json={"event_id": event["id"]},
    )

    assert active_after_leave.json() == [second_join_response.json()]
    assert rejoin_response.status_code == 201
    assert rejoin_response.json()["id"] != join_response.json()["id"]
    assert rejoin_response.json()["left_at"] is None


def test_only_organizer_can_update_event(application) -> None:
    client = TestClient(create_fastapi_app(application))
    now = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
    first_location = application.create_location(
        location=Location(address="Original place", created_at=now)
    )
    second_location = application.create_location(
        location=Location(address="Updated place", created_at=now)
    )
    event = client.post(
        "/events",
        headers={"Authorization": "Bearer darwin"},
        json={
            "title": "Original event",
            "scheduled_at": None,
            "duration_in_minutes": 60,
            "location_id": first_location.id,
        },
    ).json()

    forbidden = client.patch(
        f"/events/{event['id']}",
        headers={"Authorization": "Bearer another-user"},
        json={"title": "Unauthorized"},
    )
    updated = client.patch(
        f"/events/{event['id']}",
        headers={"Authorization": "Bearer darwin"},
        json={
            "title": "Updated event",
            "scheduled_at": "2026-09-01T20:00:00+02:00",
            "duration_in_minutes": 90,
            "location_id": second_location.id,
        },
    )
    current = client.get(f"/events/{event['id']}")

    assert forbidden.status_code == 403
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated event"
    assert updated.json()["organizer"] == "darwin"
    assert updated.json()["scheduled_at"] == "2026-09-01T18:00:00Z"
    assert updated.json()["duration_in_minutes"] == 90
    assert updated.json()["location_id"] == second_location.id

    current_json = current.json()
    assert current_json["title"] == "Updated event"

    if "location" in current_json and "created_at" in current_json["location"]:
        del current_json["location"]["created_at"]
    assert current_json["location"] == second_location.model_dump(mode="json", exclude={"created_at"})


def test_update_requires_identity_and_valid_payload(client) -> None:
    missing_identity = client.patch("/events/1", json={"title": "No actor"})
    empty_update = client.patch(
        "/events/1",
        headers={"Authorization": "Bearer darwin"},
        json={},
    )
    immutable_organizer = client.patch(
        "/events/1",
        headers={"Authorization": "Bearer darwin"},
        json={"organizer": "another-user"},
    )

    assert missing_identity.status_code == 401
    assert empty_update.status_code == 422
    assert immutable_organizer.status_code == 422


def test_http_logging_exposes_request_context_and_transaction_id(
    client,
    caplog,
) -> None:
    with caplog.at_level(
        logging.INFO,
        logger="src.entrypoints.fastapi.users.fastapi_app",
    ):
        response = client.get(
            "/events",
            headers={"X-Transaction-ID": "frontend-request-123"},
        )

    completed = next(
        record
        for record in caplog.records
        if getattr(record, "checkpoint_id", None)
        == "http-request-completed"
    )
    assert response.status_code == 200
    assert response.headers["X-Transaction-ID"] == "frontend-request-123"
    assert completed.transaction_id == "frontend-request-123"
    assert completed.http_method == "GET"
    assert completed.http_route == "/events"
    assert completed.http_status == 200
    assert completed.duration_ms >= 0
