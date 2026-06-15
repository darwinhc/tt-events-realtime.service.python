"""SQLAlchemy engine and session management."""

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


class SQLAlchemyDatabase:
    """Own SQLAlchemy configuration without exposing it to the domain."""

    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        self.database_url = database_url
        self._prepare_sqlite_directory()
        self.engine = create_engine(database_url, echo=echo)
        if self.engine.dialect.name == "sqlite":
            event.listen(self.engine, "connect", self._configure_sqlite_connection)
        self.sessions = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def initialize(self) -> None:
        """Create all tables declared by the infrastructure models."""
        Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        """Release pooled database connections."""
        self.engine.dispose()

    def _prepare_sqlite_directory(self) -> None:
        if not self.database_url.startswith("sqlite:///"):
            return
        database_path = self.database_url.removeprefix("sqlite:///")
        if database_path == ":memory:":
            return
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _configure_sqlite_connection(
        dbapi_connection: sqlite3.Connection,
        _connection_record,
    ) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA busy_timeout = 10000")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.close()
