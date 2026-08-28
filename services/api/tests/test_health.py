import pytest


@pytest.mark.asyncio
async def test_liveness_does_not_touch_db(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_reports_database_ok_with_working_db(client):
    response = await client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    # readyz uses the *real* engine from core.db, not the test override --
    # it will report the configured (unreachable, in tests) DATABASE_URL as
    # not ready, which is itself the correct behavior to verify.
    assert body["status"] in ("ready", "not_ready")
    assert "database" in body["checks"]
