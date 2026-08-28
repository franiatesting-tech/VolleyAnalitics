from fastapi import APIRouter

from volley_api.core.db import check_db_connection

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def liveness() -> dict:
    """Liveness: process is up. No dependency checks -- a slow DB must never
    cause an orchestrator to kill and restart a perfectly healthy process."""
    return {"status": "ok"}


@router.get("/readyz")
async def readiness() -> dict:
    """Readiness: dependencies the API actually needs are reachable."""
    db_ok = await check_db_connection()
    ready = db_ok
    return {"status": "ready" if ready else "not_ready", "checks": {"database": db_ok}}
