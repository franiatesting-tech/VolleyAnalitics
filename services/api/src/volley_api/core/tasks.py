"""Thin Celery client used only to enqueue tasks by name. The API never
imports services/worker's code directly (that would couple two independently
deployable processes) -- task name agreement lives in
volley_domain.tasks.PROCESS_DEMO_MATCH_TASK_NAME, the one place both sides
import it from.
"""

from functools import lru_cache

from celery import Celery
from volley_domain.tasks import PROCESS_DEMO_MATCH_TASK_NAME

from volley_api.core.config import get_settings

__all__ = ["PROCESS_DEMO_MATCH_TASK_NAME", "enqueue_process_demo_match"]


@lru_cache
def get_celery_client() -> Celery:
    # Cached: constructing a fresh Celery() per request re-parses broker
    # config and opens a new connection every time for no benefit.
    settings = get_settings()
    return Celery(broker=settings.valkey_url, backend=settings.valkey_url)


def enqueue_process_demo_match(match_id: str, dedup_key: str) -> str:
    """Sync (Celery's client is sync) -- callers on the async request path
    must run this via `asyncio.to_thread`, see api/routes/matches.py."""
    client = get_celery_client()
    result = client.send_task(
        PROCESS_DEMO_MATCH_TASK_NAME, kwargs={"match_id": match_id, "dedup_key": dedup_key}
    )
    return result.id
