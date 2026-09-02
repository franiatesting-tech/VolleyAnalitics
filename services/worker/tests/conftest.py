import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("VALKEY_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENV", "test")
# Unit tests stub ffprobe/StorageAdapter directly rather than shelling out
# to a real ffmpeg binary -- the D-006 license-build check is exercised for
# real in test_ffprobe.py instead (against whatever ffmpeg the test
# environment actually has), not at import time for every other test here.
os.environ.setdefault("SKIP_FFMPEG_LICENSE_CHECK", "true")
# Most of this suite tests orchestration/persistence logic unrelated to the
# far-tiling/burst-resampling features -- default them off here so a test's
# fixed queue of fake HTTP responses (see test_detection.py's _FakeClient)
# isn't silently exhausted by an unrequested extra pass/window. Tests that
# specifically exercise these features override get_settings directly
# (see test_detection.py's burst/tiling tests).
os.environ.setdefault("DETECTION_FAR_TILING_ENABLED", "false")
os.environ.setdefault("DETECTION_BURST_ENABLED", "false")

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
