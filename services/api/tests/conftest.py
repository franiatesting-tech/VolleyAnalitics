import os
import tempfile
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@unused/unused")
os.environ.setdefault("VALKEY_URL", "redis://unused:6379/0")
os.environ.setdefault("AUTH_JWKS_URL", "http://unused/.well-known/jwks.json")
os.environ.setdefault("AUTH_ISSUER", "http://unused")
os.environ.setdefault("AUTH_AUDIENCE", "unused")
os.environ.setdefault("ENV", "test")
# Video-ingest tests (test_videos.py) exercise the real local StorageAdapter
# against a throwaway directory -- never the developer's real
# LOCAL_STORAGE_DIR, and never .env's value even if one is present.
os.environ.setdefault(
    "LOCAL_STORAGE_DIR", str(Path(tempfile.gettempdir()) / "volley-api-tests-storage")
)
os.environ.setdefault("LOCAL_STORAGE_BASE_URL", "http://test")
os.environ.setdefault("LOCAL_STORAGE_SIGNING_SECRET", "test-only-signing-secret")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from volley_api.core.auth import Principal, get_current_principal
from volley_api.core.db import get_db
from volley_api.main import app
from volley_domain.models import Base

TEST_PRINCIPAL = Principal(user_id="user-1", organization_id="org-1", role="owner")
OTHER_ORG_PRINCIPAL = Principal(user_id="user-2", organization_id="org-2", role="owner")


@pytest_asyncio.fixture()
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite doesn't enforce foreign keys (including ON DELETE
    # CASCADE/SET NULL) unless told to per-connection -- without this,
    # every real DB-level cascade (e.g. deleting a Video/Match) silently
    # does nothing in tests while working correctly against real Postgres,
    # which always enforces FKs. Matches the identical pattern already
    # used in packages/domain-py's own cascade tests.
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
def override_principal():
    """Mutable holder so individual tests can swap which principal the app
    sees, without re-registering the whole dependency override each time."""
    return {"value": TEST_PRINCIPAL}


@pytest.fixture()
def other_org_principal():
    """A second tenant identity without importing pytest's conftest as a module."""
    return OTHER_ORG_PRINCIPAL


@pytest_asyncio.fixture()
async def client(db_engine, override_principal, monkeypatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _get_db_override():
        async with session_factory() as session:
            yield session

    async def _get_principal_override():
        return override_principal["value"]

    # Celery isn't running in unit tests -- enqueue is stubbed to a no-op
    # that returns a fake task id, so route logic can be tested without a
    # live broker. Worker-side task logic has its own tests (services/worker/tests).
    class _FakeAsyncResult:
        id = "fake-celery-task-id"

    class _FakeCeleryClient:
        def send_task(self, *args, **kwargs):
            return _FakeAsyncResult()

    monkeypatch.setattr("volley_api.core.tasks.get_celery_client", lambda: _FakeCeleryClient())

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_current_principal] = _get_principal_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
