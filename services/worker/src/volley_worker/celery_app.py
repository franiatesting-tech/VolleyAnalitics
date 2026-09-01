from celery import Celery

from volley_worker.config import get_settings
from volley_worker.ffprobe import (
    FfmpegLicenseViolationError,
    FfmpegNotFoundError,
    verify_ffmpeg_build_is_license_clean,
)

settings = get_settings()

if not settings.skip_ffmpeg_license_check:
    # D-006 (LICENSE_DECISIONS.md): fail fast at process startup in any
    # real deployment, exactly like
    # Settings._dev_auth_bypass_cannot_reach_production in services/api --
    # a worker must never silently start accepting ingest_video tasks
    # against a GPL-built ffmpeg.
    #
    # In development/test, both a missing binary AND a non-compliant one
    # are demoted to a loud warning instead of a hard crash -- verified
    # necessary during this phase: this dev machine's own system ffmpeg
    # (installed via winget for an unrelated tool) is a real GPL build,
    # and the worker also runs plenty of tasks (e.g. process_demo_match)
    # that never touch ffmpeg at all. Blocking the *entire* worker process
    # over an unrelated task type would regress a workflow that worked
    # before this check existed -- ingest_video itself still independently
    # re-verifies (see ingest.py), so a genuinely non-compliant build can
    # never actually process real video, on any host, regardless of this
    # startup check's environment-dependent strictness. Docker (this
    # project's actual supported dev/CI path, see
    # infra/docker/python.Dockerfile) always has the pinned compliant
    # build, so this soft-fail path is host-only in practice.
    try:
        verify_ffmpeg_build_is_license_clean()
    except (FfmpegNotFoundError, FfmpegLicenseViolationError) as exc:
        if settings.env not in ("development", "test"):
            raise

        import structlog

        structlog.get_logger(__name__).warning(
            "ffmpeg_license_check_failed_at_startup_non_production",
            error=str(exc),
            hint="Run via `docker compose up worker` for the pinned LGPL-only ffmpeg build. "
            "ingest_video will still refuse to run against a non-compliant build.",
        )

celery_app = Celery("volley_worker", broker=settings.valkey_url, backend=settings.valkey_url)
celery_app.conf.update(
    task_acks_late=True,  # redelivered if the worker dies mid-task, not lost
    worker_prefetch_multiplier=1,  # don't hoard tasks other workers could run
    task_default_retry_delay=10,
    task_track_started=True,
    timezone="UTC",
)

celery_app.autodiscover_tasks(["volley_worker"])
