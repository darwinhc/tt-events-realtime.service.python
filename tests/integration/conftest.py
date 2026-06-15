"""Shared cleanup for integration-test infrastructure."""

import pytest

from src.infra.database.sqlalchemy import SQLAlchemyDatabase


@pytest.fixture(autouse=True)
def dispose_created_databases(monkeypatch):
    """Dispose every database built during an integration test."""
    databases = []
    original_init = SQLAlchemyDatabase.__init__

    def tracked_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        databases.append(self)

    monkeypatch.setattr(SQLAlchemyDatabase, "__init__", tracked_init)
    yield
    for database in databases:
        database.dispose()
