import pytest


@pytest.mark.asyncio
async def test_liveness_does_not_touch_db(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_reports_database_ok_with_working_db(client, monkeypatch):
    async def _database_is_ready():
        return True

    monkeypatch.setattr("volley_api.api.routes.health.check_db_connection", _database_is_ready)
    response = await client.get("/readyz")
    body = response.json()
    assert response.status_code == 200
    assert body == {"status": "ready", "checks": {"database": True}}


@pytest.mark.asyncio
async def test_readiness_returns_503_when_database_is_unavailable(client, monkeypatch):
    async def _database_is_not_ready():
        return False

    monkeypatch.setattr("volley_api.api.routes.health.check_db_connection", _database_is_not_ready)
    response = await client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"database": False}}
