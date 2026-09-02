"""Thin Celery client used only to enqueue tasks by name. The API never
imports services/worker's code directly (that would couple two independently
deployable processes) -- task name agreement lives in
volley_domain.tasks.PROCESS_DEMO_MATCH_TASK_NAME, the one place both sides
import it from.
"""

from functools import lru_cache

from celery import Celery
from volley_domain.tasks import (
    INGEST_VIDEO_TASK_NAME,
    PROCESS_DEMO_MATCH_TASK_NAME,
    RUN_VIDEO_DETECTION_TASK_NAME,
)

from volley_api.core.config import get_settings

__all__ = [
    "INGEST_VIDEO_TASK_NAME",
    "PROCESS_DEMO_MATCH_TASK_NAME",
    "RUN_VIDEO_DETECTION_TASK_NAME",
    "enqueue_ingest_video",
    "enqueue_process_demo_match",
    "enqueue_run_video_detection",
]


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


def enqueue_ingest_video(video_id: str, storage_key: str) -> str:
    """Sync (Celery's client is sync) -- callers on the async request path
    must run this via `asyncio.to_thread`, see api/routes/videos.py."""
    client = get_celery_client()
    result = client.send_task(
        INGEST_VIDEO_TASK_NAME, kwargs={"video_id": video_id, "storage_key": storage_key}
    )
    return result.id


def enqueue_run_video_detection(
    pipeline_run_id: str,
    video_id: str,
    max_duration_seconds: float | None = None,
    start_offset_seconds: float | None = None,
    sample_fps: float | None = None,
) -> str:
    """Sync (Celery's client is sync) -- callers on the async request path
    must run this via `asyncio.to_thread`, see api/routes/videos.py."""
    client = get_celery_client()
    result = client.send_task(
        RUN_VIDEO_DETECTION_TASK_NAME,
        kwargs={
            "pipeline_run_id": pipeline_run_id,
            "video_id": video_id,
            "max_duration_seconds": max_duration_seconds,
            "start_offset_seconds": start_offset_seconds,
            "sample_fps": sample_fps,
        },
    )
    return result.id
