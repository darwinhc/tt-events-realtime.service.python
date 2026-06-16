"""Alembic migration environment for Events Service.

This file keeps migrations aligned with the application's SQLAlchemy models and
runtime configuration. The database URL is resolved from the same settings object
used by the FastAPI and job entrypoints.
"""

from __future__ import annotations

import sqlite3
import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from alembic import context
from sqlalchemy import event, pool
from sqlalchemy.engine import Connection
from sqlalchemy import engine_from_config

# Alembic Config object. It provides access to values within alembic.ini.
config = context.config

# Configure Python logging from alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Ensure the repository root is importable when Alembic is executed from a
# different working directory. This complements `prepend_sys_path = .` in
# alembic.ini and makes the file more robust in CI/CD.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.infra.config import get_settings  # noqa: E402
from src.infra.database.sqlalchemy.models import Base  # noqa: E402

# Metadata used by Alembic autogenerate.
target_metadata = Base.metadata


def _get_database_url() -> str:
    """Resolve the database URL for migrations.

    Priority:
    1. `alembic -x database_url=...`
    2. Application settings loaded from environment variables / .env
    3. `sqlalchemy.url` fallback from alembic.ini
    """
    x_arguments = context.get_x_argument(as_dictionary=True)
    database_url = x_arguments.get("database_url")
    if database_url:
        return database_url

    settings_url = get_settings().database_url
    if settings_url:
        return settings_url

    main_option = config.get_main_option("sqlalchemy.url")
    if main_option is None:
        raise ValueError("No database URL provided")
    return main_option


def _prepare_sqlite_directory(database_url: str) -> None:
    """Create the parent directory for file-based SQLite databases."""
    if not database_url.startswith("sqlite:///"):
        return

    database_path = database_url.removeprefix("sqlite:///")
    if database_path == ":memory:":
        return

    Path(database_path).parent.mkdir(parents=True, exist_ok=True)


def _configure_sqlite_connection(
    dbapi_connection: sqlite3.Connection,
    _connection_record: Any,
) -> None:
    """Apply the same SQLite pragmas used by the application database adapter."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA busy_timeout = 10000")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.close()


def _configure_context(connection: Connection | None = None) -> dict[str, Any]:
    """Build the common Alembic context configuration."""
    context_options: dict[str, Any] = {
        "target_metadata": target_metadata,
        "compare_type": True,
        "compare_server_default": True,
        "render_as_batch": True,
        # This makes autogenerate render custom types as
        # `sqlalchemy_types.UTCDateTime()` instead of using a long module path.
        # The generated migration template imports this alias.
        "user_module_prefix": "sqlalchemy_types.",
    }

    if connection is not None:
        context_options["connection"] = connection
    else:
        context_options["url"] = _get_database_url()
        context_options["literal_binds"] = True
        context_options["dialect_opts"] = {"paramstyle": "named"}

    return context_options


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine.

    Offline mode emits SQL to the script output instead of executing it against a
    live database connection.
    """
    database_url = _get_database_url()
    _prepare_sqlite_directory(database_url)
    config.set_main_option("sqlalchemy.url", database_url)

    context.configure(**_configure_context())

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    database_url = _get_database_url()
    _prepare_sqlite_directory(database_url)
    config.set_main_option("sqlalchemy.url", database_url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    if connectable.dialect.name == "sqlite":
        event.listen(connectable, "connect", _configure_sqlite_connection)

    with connectable.connect() as connection:
        context.configure(**_configure_context(connection))

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
