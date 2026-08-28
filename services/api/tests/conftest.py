import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@unused/unused")
os.environ.setdefault("VALKEY_URL", "redis://unused:6379/0")
os.environ.setdefault("AUTH_JWKS_URL", "http://unused/.well-known/jwks.json")
os.environ.setdefault("AUTH_ISSUER", "http://unused")
os.environ.setdefault("AUTH_AUDIENCE", "unused")
os.environ.setdefault("ENV", "test")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
def override_principal():
    """Mutable holder so individual tests can swap which principal the app
    sees, without re-registering the whole dependency override each time."""
    return {"value": TEST_PRINCIPAL}


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
