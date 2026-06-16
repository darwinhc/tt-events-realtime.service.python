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
