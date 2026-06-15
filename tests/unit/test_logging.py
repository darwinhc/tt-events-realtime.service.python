"""Portable logging configuration tests."""

import json
import logging

from src.infra.config import Settings
from src.infra.logging import configure_logging


def build_settings(**overrides) -> Settings:
    values = {
        "app_name": "events-service",
        "environment": "test",
        "database_url": "sqlite:///:memory:",
        "sqlalchemy_echo": False,
        "log_level": "INFO",
        "log_format": "json",
        "cloudwatch_enabled": False,
        "cloudwatch_group": "/tests/events-service",
        "cloudwatch_stream": "test",
        "aws_region": "eu-central-1",
    }
    values.update(overrides)
    return Settings(**values)


def test_json_logging_contains_service_and_trace_context(capsys) -> None:
    configure_logging(build_settings())

    logging.getLogger("test.logger").info(
        "Event accepted",
        extra={
            "transaction_id": "transaction-123",
            "checkpoint_id": "event-accepted",
            "event_id": 42,
        },
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["message"] == "Event accepted"
    assert payload["service"] == "events-service"
    assert payload["environment"] == "test"
    assert payload["transaction_id"] == "transaction-123"
    assert payload["checkpoint_id"] == "event-accepted"
    assert payload["event_id"] == 42
    assert "exc_info" not in payload


def test_json_logging_removes_noisy_uvicorn_internal_fields(capsys) -> None:
    configure_logging(build_settings())

    logging.getLogger("uvicorn.error").warning(
        "WebSocket closed",
        extra={
            "websocket": object(),
            "checkpoint_id": "websocket-closed",
        },
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["message"] == "WebSocket closed"
    assert payload["checkpoint_id"] == "websocket-closed"
    assert "websocket" not in payload


def test_logging_configuration_is_idempotent() -> None:
    settings = build_settings()

    configure_logging(settings)
    configure_logging(settings)

    managed_handlers = [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, "_events_service_handler", False)
    ]
    assert len(managed_handlers) == 1


def test_cloudwatch_handler_can_be_enabled(monkeypatch) -> None:
    created_handlers = []

    class FakeCloudWatchHandler(logging.Handler):
        def __init__(self, **kwargs) -> None:
            super().__init__()
            self.options = kwargs
            created_handlers.append(self)

    class FakeBoto3:
        @staticmethod
        def client(service_name, region_name):
            return {"service_name": service_name, "region_name": region_name}

    class FakeWatchtower:
        CloudWatchLogHandler = FakeCloudWatchHandler

    monkeypatch.setitem(__import__("sys").modules, "boto3", FakeBoto3)
    monkeypatch.setitem(__import__("sys").modules, "watchtower", FakeWatchtower)

    configure_logging(build_settings(cloudwatch_enabled=True))

    assert len(created_handlers) == 1
    assert created_handlers[0].options["log_group_name"] == "/tests/events-service"
    assert created_handlers[0].options["log_stream_name"] == "test"
