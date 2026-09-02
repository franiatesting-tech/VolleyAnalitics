"""INGEST_VIDEO: computes video_hash (SHA-256), probes the container/codec
via ffprobe, and persists the result onto the `Video` row the API already
created at upload-URL-issuance time -- see
services/api/src/volley_api/api/routes/videos.py and
docs/architecture/DATA_FLOW.md's upload lifecycle ("worker computes
video_hash, probes container/codec/PTS, ... persists metadata to
PostgreSQL").

Idempotency: keyed by `video_id` (one Video row per upload). Re-running
against the same uploaded bytes recomputes the same SHA-256 deterministically
and is therefore always safe to retry -- there is no partial-write hazard
since the whole probe+hash step happens before any DB write, and the single
DB write below is one transaction (status + hash + probe fields flip
together, matching process_demo_match's "persistence and status flip in one
transaction" pattern in tasks.py).

Duplicate detection: if the computed hash already belongs to a different
Video row in the same organization, this run is marked FAILED with a
descriptive error rather than letting the DB's unique constraint
(`uq_video_org_hash`) raise an opaque IntegrityError. This is a deliberate
simplification for this phase -- a real product might instead offer to link
the new upload to the existing Video rather than reject it outright; see
TECH_DEBT.md.
"""

import hashlib
import tempfile
from pathlib import Path

import structlog
from volley_domain.ontology import (
    ModelRun,
    ModelRunStage,
    PipelineRun,
    PipelineRunStatus,
    Video,
    VideoStatus,
)
from volley_domain.tasks import INGEST_VIDEO_TASK_NAME

from volley_worker.celery_app import celery_app
from volley_worker.db import session_scope
from volley_worker.ffprobe import (
    FfmpegLicenseViolationError,
    FfmpegNotFoundError,
    FfprobeFailedError,
    UnsafeMediaFileError,
    compute_sha256,
    get_ffprobe_build_fingerprint,
    probe_video,
    verify_ffmpeg_build_is_license_clean,
)
from volley_worker.storage import get_storage_adapter

# Bump whenever probe_video's own extraction logic materially changes
# (e.g. a new field, a different PTS-mapping rule) -- distinct from the
# ffmpeg *build*'s own identity, which is captured separately in each
# ModelRun's config_hash below.
_INGEST_PIPELINE_VERSION = "ingest-v1"

logger = structlog.get_logger(__name__)


@celery_app.task(
    bind=True,
    name=INGEST_VIDEO_TASK_NAME,
    max_retries=3,
    default_retry_delay=10,
)
def ingest_video(self, video_id: str, storage_key: str) -> dict:
    log = logger.bind(video_id=video_id, storage_key=storage_key, celery_task_id=self.request.id)

    with session_scope() as db:
        video = db.get(Video, video_id)
        if video is None:
            log.error("ingest_video_missing_video_row")
            raise ValueError(f"No Video found for video_id={video_id}")
        if video.status == VideoStatus.READY:
            log.info("ingest_video_already_ready_noop")
            return {"status": "already_ready", "video_id": video_id}
        organization_id = video.organization_id
        # This task trusts both of its own arguments (video_id, storage_key)
        # with no cross-check between them -- anyone able to enqueue a task
        # on Valkey (not just the API) could otherwise point one org's Video
        # row at another org's storage key. storage_key is always
        # constructed as f"{organization_id}/..." by the API
        # (routes/videos.py) -- enforce that shape holds here too. Caught
        # by independent security review.
        if not storage_key.startswith(f"{organization_id}/"):
            log.error(
                "ingest_video_storage_key_org_mismatch",
                video_org=organization_id,
            )
            raise ValueError(f"storage_key does not belong to video {video_id}'s organization")
        video.status = VideoStatus.VALIDATING
        video.error = None

    try:
        # Defense in depth: celery_app.py already runs this once at process
        # startup (fail fast before accepting any task at all), but a
        # per-task re-check costs nothing and catches a base image/PATH
        # change that happened without a worker process restart.
        verify_ffmpeg_build_is_license_clean()

        adapter = get_storage_adapter()
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_path = adapter.download_to_path(storage_key, Path(tmp_dir) / "source")
            video_hash = compute_sha256(local_path)
            probe = probe_video(local_path)
        # Provenance for the probe fields written below -- which ffmpeg
        # *build* produced them, not just that ffprobe ran. Same build can
        # legitimately read the same container differently across
        # versions, so this is the config_hash the PipelineRun idempotency
        # key (DATA_FLOW.md: video_hash + pipeline_version + config_hash)
        # actually needs. See TECH_DEBT.md's now-fixed "Ingest creates no
        # PipelineRun/ModelRun row" entry.
        ffprobe_version_line, ffprobe_config_line = get_ffprobe_build_fingerprint()
        ingest_config_hash = hashlib.sha256(
            f"{_INGEST_PIPELINE_VERSION}:{ffprobe_config_line}".encode()
        ).hexdigest()

        with session_scope() as db:
            duplicate = (
                db.query(Video)
                .filter(
                    Video.organization_id == organization_id,
                    Video.video_hash == video_hash,
                    Video.id != video_id,
                )
                .one_or_none()
            )
            video = db.get(Video, video_id)
            if video is None:
                # Existence was already confirmed at the top of this task;
                # a row disappearing between then and now would mean
                # something else deleted it mid-flight -- fail loud rather
                # than silently swallow it (no silent TODOs on this path).
                raise ValueError(f"Video {video_id} disappeared during ingest")

            if duplicate is not None:
                video.status = VideoStatus.FAILED
                video.error = (
                    f"Duplicate content: identical video_hash already exists as "
                    f"video {duplicate.id} in this organization"
                )
                log.info("ingest_video_duplicate_detected", duplicate_of=duplicate.id)
                return {"status": "duplicate", "video_id": video_id, "duplicate_of": duplicate.id}

            pipeline_run = PipelineRun(
                video_id=video_id,
                pipeline_version=_INGEST_PIPELINE_VERSION,
                config_hash=ingest_config_hash,
                status=PipelineRunStatus.COMPLETED,
            )
            db.add(pipeline_run)
            db.flush()
            db.add(
                ModelRun(
                    pipeline_run_id=pipeline_run.id,
                    stage=ModelRunStage.INGEST,
                    model_version=ffprobe_version_line or "ffprobe-unknown",
                    metrics={
                        "codec": probe.codec,
                        "container_format": probe.container_format,
                        "fps": probe.fps,
                        "width": probe.width,
                        "height": probe.height,
                        "duration_seconds": probe.duration_seconds,
                    },
                )
            )

            video.video_hash = video_hash
            video.codec = probe.codec
            video.duration_seconds = probe.duration_seconds
            video.fps = probe.fps
            video.width = probe.width
            video.height = probe.height
            video.start_time_seconds = probe.start_time_seconds
            video.time_base = probe.time_base
            video.status = VideoStatus.READY

        log.info(
            "ingest_video_completed",
            video_hash=video_hash,
            codec=probe.codec,
            duration_seconds=probe.duration_seconds,
            fps=probe.fps,
        )
        return {"status": "ready", "video_id": video_id, "video_hash": video_hash}

    except (FfmpegLicenseViolationError, UnsafeMediaFileError) as exc:
        # Deliberately NOT retried, unlike the group below -- neither
        # condition is transient. A non-compliant ffmpeg build will still
        # be non-compliant in 10 seconds (retrying it three times before
        # failing was flagged by independent review as semantically wrong
        # and as burying a license-compliance failure inside generic retry
        # noise), and a file that looks like a text-based reference format
        # will still look like one. Fail once, loudly, immediately.
        log.exception("ingest_video_failed_terminal")
        with session_scope() as db:
            video = db.get(Video, video_id)
            if video:
                video.status = VideoStatus.FAILED
                video.error = str(exc)
        raise
    except (FfmpegNotFoundError, FfprobeFailedError) as exc:
        # Same uniform bounded-retry-then-fail treatment as
        # process_demo_match -- see that task's module docstring for why a
        # genuine bug and a transient failure get the same handling here
        # rather than trying to enumerate every transient-vs-permanent case.
        log.exception("ingest_video_failed")
        with session_scope() as db:
            video = db.get(Video, video_id)
            if video:
                video.status = VideoStatus.FAILED
                video.error = str(exc)
        raise self.retry(exc=exc) from exc
    except Exception as exc:
        log.exception("ingest_video_failed")
        with session_scope() as db:
            video = db.get(Video, video_id)
            if video:
                video.status = VideoStatus.FAILED
                video.error = str(exc)
        raise self.retry(exc=exc) from exc
