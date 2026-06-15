"""Structured logging configuration for FastAPI runtime."""

import logging
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from src.infra.config import Settings
from .context import get_transaction_id

_MANAGED_HANDLER_MARKER = "_events_service_handler"


class ServiceContextFilter(logging.Filter):
    """Attach service and tracing context to every log record."""

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._settings.app_name
        record.environment = self._settings.environment

        if not hasattr(record, "transaction_id"):
            record.transaction_id = get_transaction_id() or "no-transaction"

        if not hasattr(record, "checkpoint_id"):
            record.checkpoint_id = "unclassified"

        for noisy_field in ("websocket", "scope"):
            if hasattr(record, noisy_field):
                delattr(record, noisy_field)

        return True

class UTCTextFormatter(logging.Formatter):
    """Render human-readable timestamps consistently in UTC."""

    converter = time.gmtime

    def formatTime(self, record, datefmt=None) -> str:
        return datetime.fromtimestamp(
            record.created,
            tz=timezone.utc,
        ).isoformat(timespec="milliseconds")


def _build_formatter() -> logging.Formatter:
    return UTCTextFormatter(
        (
            "%(asctime)s %(levelname)s %(name)s "
            "[service=%(service)s][environment=%(environment)s]"
            "[transaction_id=%(transaction_id)s][checkpoint_id=%(checkpoint_id)s] "
            "%(message)s"
        )
    )


def _build_stream_handler(
    settings: Settings,
    formatter: logging.Formatter,
    context_filter: logging.Filter,
) -> logging.Handler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(settings.log_level)
    handler.setFormatter(formatter)
    handler.addFilter(context_filter)
    setattr(handler, _MANAGED_HANDLER_MARKER, True)
    return handler


def configure_logging(settings: Settings) -> None:
    """Configure stdout JSON logging for FastAPI deployments."""
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    root_logger.handlers = [
        handler
        for handler in root_logger.handlers
        if not getattr(handler, _MANAGED_HANDLER_MARKER, False)
    ]

    formatter = _build_formatter()
    context_filter = ServiceContextFilter(settings)

    root_logger.addHandler(
        _build_stream_handler(settings, formatter, context_filter)
    )

    for logger_name in (
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "fastapi",
        "sqlalchemy.engine",
    ):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True

    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a standard logger usable from any application layer."""
    return logging.getLogger(name)