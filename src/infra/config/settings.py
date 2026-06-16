"""Application settings loaded from environment variables."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized_value = value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value.")


def _read_choice(name: str, default: str, choices: set[str]) -> str:
    value = os.getenv(name, default).strip().lower()
    if value not in choices:
        expected_values = ", ".join(sorted(choices))
        raise ValueError(f"{name} must be one of: {expected_values}.")
    return value


def _read_non_negative_int(name: str, default: int) -> int:
    value = os.getenv(name, str(default)).strip()
    try:
        parsed_value = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a non-negative integer.") from error
    if parsed_value < 0:
        raise ValueError(f"{name} must be a non-negative integer.")
    return parsed_value


class Settings(BaseModel):
    """Runtime configuration shared by all entry points."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    app_name: str
    environment: str
    database_url: str
    sqlalchemy_echo: bool
    log_level: str
    log_format: str
    cloudwatch_enabled: bool
    cloudwatch_group: str
    cloudwatch_stream: str
    aws_region: str
    event_deletion_delay_minutes: int = 7*60*24
    location_unused_deletion_delay_minutes: int = 90
    canceled_event_deletion_delay_minutes: int = 90
    cors_allowed_origins: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load `.env` defaults while preserving real environment overrides."""
    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env", override=False)

    app_name = os.getenv("APP_NAME", "events-service").strip()
    environment = os.getenv("APP_ENV", "development").strip()
    database_url = os.getenv(
        "EVENTS_DATABASE_URL",
        "sqlite:///data/events.db",
    ).strip()
    log_level = _read_choice(
        "LOG_LEVEL",
        "INFO",
        {"debug", "info", "warning", "error", "critical"},
    ).upper()
    log_format = _read_choice("LOG_FORMAT", "json", {"json", "text"})
    cloudwatch_group = os.getenv(
        "LOG_CLOUDWATCH_GROUP",
        f"/applications/{app_name}",
    ).strip()
    cloudwatch_stream = os.getenv(
        "LOG_CLOUDWATCH_STREAM",
        environment,
    ).strip()
    aws_region = os.getenv("AWS_REGION", "eu-central-1").strip()
    cors_allowed_origins = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    )

    required_values = {
        "APP_NAME": app_name,
        "APP_ENV": environment,
        "EVENTS_DATABASE_URL": database_url,
        "LOG_CLOUDWATCH_GROUP": cloudwatch_group,
        "LOG_CLOUDWATCH_STREAM": cloudwatch_stream,
        "AWS_REGION": aws_region,
    }
    for name, value in required_values.items():
        if not value:
            raise ValueError(f"{name} cannot be empty.")

    return Settings(
        app_name=app_name,
        environment=environment,
        database_url=database_url,
        sqlalchemy_echo=_read_bool("SQLALCHEMY_ECHO", False),
        log_level=log_level,
        log_format=log_format,
        cloudwatch_enabled=_read_bool("LOG_CLOUDWATCH_ENABLED", False),
        cloudwatch_group=cloudwatch_group,
        cloudwatch_stream=cloudwatch_stream,
        aws_region=aws_region,
        event_deletion_delay_minutes=_read_non_negative_int(
            "EVENT_DELETION_DELAY_MINUTES",
            7,
        ),
        canceled_event_deletion_delay_minutes=_read_non_negative_int(
            "CANCELED_EVENT_DELETION_DELAY_MINUTES",
            1,
        ),
        cors_allowed_origins=cors_allowed_origins,
    )
