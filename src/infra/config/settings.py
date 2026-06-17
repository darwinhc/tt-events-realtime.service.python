"""Application settings loaded from environment variables."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from .utils import read_bool, read_choice, read_non_negative_int

class Settings(BaseModel):
    """Runtime configuration shared by all entry points."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    app_name: str
    environment: str
    database_url: str
    sqlalchemy_echo: bool
    log_level: str
    event_deletion_delay_minutes: int = 120
    event_deletion_delay_when_no_date_in_minutes: int = 7*24*60
    location_unused_deletion_delay_minutes: int = 90
    canceled_event_deletion_delay_minutes: int = 90
    cors_allowed_origins: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load `.env` defaults while preserving real environment overrides."""
    project_root = Path(__file__).resolve().parents[3]

    env_file = os.getenv("EVENTS_ENV_FILE", ".env").strip()

    if env_file.lower() not in {"", "none", "false"}:
        env_path = Path(env_file)

        if not env_path.is_absolute():
            env_path = project_root / env_path

        load_dotenv(env_path, override=False)

    app_name = os.getenv("APP_NAME", "events-service").strip()
    environment = os.getenv("APP_ENV", "development").strip()
    database_url = os.getenv(
        "EVENTS_DATABASE_URL",
        "sqlite:///data/events.db",
    ).strip()
    log_level = read_choice(
        "LOG_LEVEL",
        "INFO",
        {"debug", "info", "warning", "error", "critical"},
    ).upper()
    cors_allowed_origins = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    )

    required_values = {
        "APP_NAME": app_name,
        "APP_ENV": environment,
        "EVENTS_DATABASE_URL": database_url,
    }
    for name, value in required_values.items():
        if not value:
            raise ValueError(f"{name} cannot be empty.")

    return Settings(
        app_name=app_name,
        environment=environment,
        database_url=database_url,
        sqlalchemy_echo=read_bool("SQLALCHEMY_ECHO", False),
        log_level=log_level,
        event_deletion_delay_minutes=read_non_negative_int(
            "EVENT_DELETION_DELAY_MINUTES",
            120,
        ),
        event_deletion_delay_when_no_date_in_minutes=read_non_negative_int(
            "EVENT_DELETION_DELAY_WHEN_NO_DATE_IN_MINUTES",
            7*24*60,
        ),
        canceled_event_deletion_delay_minutes=read_non_negative_int(
            "CANCELED_EVENT_DELETION_DELAY_MINUTES",
            120,
        ),
        location_unused_deletion_delay_minutes=read_non_negative_int(
            "LOCATION_UNUSED_DELETION_DELAY_MINUTES",
            90*24*60,
        ),
        cors_allowed_origins=cors_allowed_origins,
    )
