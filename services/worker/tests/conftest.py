import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("VALKEY_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENV", "test")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from volley_domain.models import Base


@pytest.fixture()
def sqlite_session_factory(monkeypatch):
    """In-memory SQLite standing in for Postgres in unit tests -- fast,
    no external service required. Integration tests against real Postgres
    live in services/api/tests (see docker-compose test profile)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    import volley_worker.db as db_module

    monkeypatch.setattr(db_module, "_SessionFactory", factory)
    return factory
