"""RUN_VIDEO_DETECTION: exploratory, non-ground-truth per-frame person-box
detection for a real uploaded Video -- see VideoDetectionFrame's docstring
in ontology.py for the full "why a separate table from PlayerObservation"
rationale.

This task deliberately never imports torch/rfdetr itself. services/worker's
Docker image is kept lightweight (see docker-compose.yml) -- real inference
runs in a small FastAPI process the operator starts on the host from ml/'s
own `inference`+`server` extras venv (volley_ml.detection.server), reached
here over HTTP via Docker Desktop's `host.docker.internal` hostname. This
task's own job is orchestration only: extract frames at a fixed low sample
rate (CPU-only local inference is far too slow to run every frame of a full
match), call the inference server per frame, and persist the results with
full PipelineRun/ModelRun provenance.

If the inference server isn't running, this fails loudly with an actionable
error rather than silently producing an empty/fabricated result -- see the
`httpx.ConnectError` branch below.

Idempotency: keyed by `pipeline_run_id` (one row per detection attempt --
see routes/videos.py's POST /videos/{id}/detect, which creates a fresh
PipelineRun per attempt rather than reusing a FAILED one, matching
PipelineRun's own "one execution" docstring). Retrying an already-COMPLETED
run is a no-op.

Progress/partial-durability: the `ModelRun` row (with `frames_total` in its
metrics) is created *before* the per-frame loop starts, and each
`VideoDetectionFrame` is committed as soon as its own frame finishes --
never batched into one final transaction. This is what makes real progress
("N of `frames_total` frames done") queryable from the API while a long run
is still in flight, and it means a worker crash/restart mid-run no longer
discards everything that had already been processed (see TECH_DEBT.md's
"a real incident, not a hypothetical" entry -- this fixes exactly the gap
that entry names). A retry of the *same* `pipeline_run_id` still restarts
frame extraction from the beginning rather than resuming past where it left
off (true resume-by-frame-index isn't implemented yet) -- but it does clear
out the stale `ModelRun`/`VideoDetectionFrame` rows from the abandoned
attempt first, so no orphaned partial data or duplicate `ModelRun` rows
accumulate.
"""

import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog
from volley_domain.ontology import (
    ModelRun,
    ModelRunStage,
    PipelineRun,
    PipelineRunStatus,
    Video,
    VideoAsset,
    VideoAssetKind,
    VideoDetectionFrame,
)
from volley_domain.tasks import DETECTION_PIPELINE_VERSION, RUN_VIDEO_DETECTION_TASK_NAME

from volley_worker.ball_filtering import find_static_false_positive_ids
from volley_worker.celery_app import celery_app
from volley_worker.config import get_settings
from volley_worker.db import session_scope
from volley_worker.frame_extraction import FrameExtractionFailedError, extract_frames_at_fps
from volley_worker.storage import get_storage_adapter

logger = structlog.get_logger(__name__)

# Generous relative to RFDETR_NANO_SMOKE.md's observed ~0.4-1.7s/frame on
# CPU -- covers a slower real frame or transient host contention without
# masking a genuinely hung inference server behind an over-long wait.
_HEALTH_CHECK_TIMEOUT_SECONDS = 120.0
_PER_FRAME_TIMEOUT_SECONDS = 30.0


def _config_hash(*, sample_fps: float, threshold: float) -> str:
    """The API creates each PipelineRun row with a placeholder config_hash
    (see routes/videos.py's trigger_video_detection) since sample_fps/
    threshold are worker-side runtime settings it has no authoritative view
    of -- this recomputes the real value from what this task actually ran
    with and overwrites it in the same transaction as the COMPLETED status
    flip below, so the persisted row always reflects ground truth, not a
    guess made before execution."""
    payload = json.dumps(
        {
            "pipeline_version": DETECTION_PIPELINE_VERSION,
            "sample_fps": sample_fps,
            "threshold": threshold,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


@celery_app.task(
    bind=True,
    name=RUN_VIDEO_DETECTION_TASK_NAME,
    max_retries=3,
    default_retry_delay=10,
)
def run_video_detection(
    self,
    pipeline_run_id: str,
    video_id: str,
    max_duration_seconds: float | None = None,
    start_offset_seconds: float | None = None,
    sample_fps: float | None = None,
) -> dict:
    log = logger.bind(
        pipeline_run_id=pipeline_run_id, video_id=video_id, celery_task_id=self.request.id
    )
    settings = get_settings()
    # A caller-supplied rate overrides the env default -- lets a coach
    # deliberately pay for a much denser ball-motion sample (paired with
    # start_offset_seconds/max_duration_seconds to scope it to one short,
    # important stretch) without redeploying the worker for every run.
    effective_sample_fps = sample_fps if sample_fps is not None else settings.detection_sample_fps

    with session_scope() as db:
        pipeline_run = db.get(PipelineRun, pipeline_run_id)
        if pipeline_run is None:
            log.error("run_video_detection_missing_pipeline_run")
            raise ValueError(f"No PipelineRun found for pipeline_run_id={pipeline_run_id}")
        if pipeline_run.status == PipelineRunStatus.COMPLETED:
            log.info("run_video_detection_already_completed_noop")
            return {"status": "already_completed", "pipeline_run_id": pipeline_run_id}

        video = db.get(Video, video_id)
        if video is None:
            log.error("run_video_detection_missing_video_row")
            raise ValueError(f"No Video found for video_id={video_id}")

        asset = (
            db.query(VideoAsset)
            .filter_by(video_id=video_id, kind=VideoAssetKind.ORIGINAL)
            .one_or_none()
        )
        if asset is None:
            pipeline_run.status = PipelineRunStatus.FAILED
            pipeline_run.error = "No original storage reference found for this video"
            log.error("run_video_detection_missing_asset")
            return {"status": "failed", "pipeline_run_id": pipeline_run_id}
        storage_key = asset.storage_ref

        # A retry of this same pipeline_run_id (after a transient failure)
        # restarts frame extraction from scratch -- clear out whatever
        # ModelRun/VideoDetectionFrame rows the abandoned attempt already
        # committed first, both because the (model_run_id, frame_index)
        # unique constraint would otherwise reject the re-inserts, and
        # because the API's status/detections lookups assume at most one
        # DETECTION ModelRun per PipelineRun.
        stale_model_run = (
            db.query(ModelRun)
            .filter_by(pipeline_run_id=pipeline_run_id, stage=ModelRunStage.DETECTION)
            .one_or_none()
        )
        if stale_model_run is not None:
            db.query(VideoDetectionFrame).filter_by(model_run_id=stale_model_run.id).delete()
            db.delete(stale_model_run)
            log.info("run_video_detection_cleared_stale_model_run", model_run_id=stale_model_run.id)

        pipeline_run.status = PipelineRunStatus.RUNNING

    try:
        with httpx.Client(timeout=_HEALTH_CHECK_TIMEOUT_SECONDS) as client:
            health_response = client.get(f"{settings.detection_inference_url}/health")
            health_response.raise_for_status()
        health = health_response.json()
        model_version = health["model_version"]
        weights_sha256 = health["weights_sha256"]

        adapter = get_storage_adapter()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            local_video = adapter.download_to_path(storage_key, tmp_path / "source")
            frame_paths = extract_frames_at_fps(
                local_video,
                tmp_path / "frames",
                fps=effective_sample_fps,
                max_duration_seconds=max_duration_seconds,
                start_offset_seconds=start_offset_seconds,
            )
            if not frame_paths:
                raise FrameExtractionFailedError("ffmpeg produced no sampled frames for this video")

            # Created *before* the frame loop, with frames_total already
            # known, so a client polling detection-status sees real
            # progress while a long run is still in flight -- see this
            # module's docstring for the full rationale.
            with session_scope() as db:
                model_run = ModelRun(
                    pipeline_run_id=pipeline_run_id,
                    stage=ModelRunStage.DETECTION,
                    model_version=model_version,
                    weights_hash=weights_sha256,
                    metrics={
                        "sample_fps": effective_sample_fps,
                        "threshold": settings.detection_threshold,
                        "ball_threshold": settings.detection_ball_threshold,
                        "max_duration_seconds": max_duration_seconds,
                        "start_offset_seconds": start_offset_seconds,
                        "frames_total": len(frame_paths),
                    },
                )
                db.add(model_run)
                db.flush()
                model_run_id = model_run.id

            person_candidates = 0
            ball_candidates = 0
            # Accumulated purely in memory (small -- a handful of ball
            # boxes per frame at most) so the static-false-positive filter
            # below can see every ball detection across the whole video
            # after the loop, without a second DB round trip.
            all_ball_detections: list[tuple[float, dict]] = []
            with httpx.Client(timeout=_PER_FRAME_TIMEOUT_SECONDS) as client:
                for ordinal, frame_path in enumerate(frame_paths, start=1):
                    # Position within the *extracted* clip, plus the
                    # skipped prefix added back -- the frontend syncs these
                    # timestamps against the real, untrimmed video's own
                    # <video>.currentTime, so a stored timestamp must
                    # always mean "seconds into the original video," never
                    # "seconds into whatever ffmpeg happened to extract."
                    timestamp_seconds = (ordinal - 1) / effective_sample_fps + (
                        start_offset_seconds or 0.0
                    )
                    with frame_path.open("rb") as source_file:
                        response = client.post(
                            f"{settings.detection_inference_url}/detect-frame",
                            files={"image": (frame_path.name, source_file, "image/jpeg")},
                            data={
                                "threshold": str(settings.detection_threshold),
                                "ball_threshold": str(settings.detection_ball_threshold),
                            },
                        )
                    response.raise_for_status()
                    payload = response.json()
                    width, height = payload["image_width"], payload["image_height"]
                    detections = [
                        {
                            "candidate_id": f"{video_id}:{ordinal}:{index}",
                            "bbox": {
                                "x": box["x1"] / width,
                                "y": box["y1"] / height,
                                "width": (box["x2"] - box["x1"]) / width,
                                "height": (box["y2"] - box["y1"]) / height,
                            },
                            "confidence": box["confidence"],
                            "jersey_color_outlier": box["jersey_color_outlier"],
                        }
                        for index, box in enumerate(payload["boxes"])
                    ]
                    ball_detections = [
                        {
                            "candidate_id": f"{video_id}:{ordinal}:ball:{index}",
                            "bbox": {
                                "x": ball["x1"] / width,
                                "y": ball["y1"] / height,
                                "width": (ball["x2"] - ball["x1"]) / width,
                                "height": (ball["y2"] - ball["y1"]) / height,
                            },
                            "confidence": ball["confidence"],
                            # Overwritten below, once every frame has been
                            # processed and the full-video static-position
                            # filter can actually see the whole picture --
                            # see find_static_false_positive_ids's docstring.
                            "is_static_false_positive": False,
                        }
                        for index, ball in enumerate(payload["balls"])
                    ]
                    person_candidates += len(detections)
                    ball_candidates += len(ball_detections)
                    all_ball_detections.extend(
                        (timestamp_seconds, ball) for ball in ball_detections
                    )

                    # Committed per-frame, not batched -- this row existing
                    # at all is what makes progress observable mid-run and
                    # survivable across a worker restart.
                    with session_scope() as db:
                        db.add(
                            VideoDetectionFrame(
                                video_id=video_id,
                                model_run_id=model_run_id,
                                frame_index=ordinal,
                                timestamp_seconds=timestamp_seconds,
                                detections=detections,
                                ball_detections=ball_detections,
                            )
                        )

        static_false_positive_ids = find_static_false_positive_ids(all_ball_detections)
        if static_false_positive_ids:
            log.info(
                "run_video_detection_flagged_static_ball_false_positives",
                count=len(static_false_positive_ids),
                of_total=len(all_ball_detections),
            )
            with session_scope() as db:
                # Filtering `ball_detections != []` isn't reliable across
                # both this project's DB backends (SQLite in tests vs.
                # Postgres in real use) at the SQL level for a JSON column
                # -- fetched and filtered in Python instead, same as this
                # module's other per-model_run queries.
                frames = db.query(VideoDetectionFrame).filter_by(model_run_id=model_run_id).all()
                for frame in frames:
                    if not frame.ball_detections:
                        continue
                    updated = [
                        {
                            **ball,
                            "is_static_false_positive": ball["candidate_id"]
                            in static_false_positive_ids,
                        }
                        for ball in frame.ball_detections
                    ]
                    if updated != frame.ball_detections:
                        frame.ball_detections = updated

        with session_scope() as db:
            pipeline_run = db.get(PipelineRun, pipeline_run_id)
            if pipeline_run is None:
                raise ValueError(f"PipelineRun {pipeline_run_id} disappeared during detection")
            model_run = db.get(ModelRun, model_run_id)
            if model_run is None:
                raise ValueError(f"ModelRun {model_run_id} disappeared during detection")

            model_run.completed_at = datetime.now(UTC)
            model_run.metrics = {
                **(model_run.metrics or {}),
                "frames_processed": len(frame_paths),
                "person_candidates": person_candidates,
                "ball_candidates": ball_candidates,
            }

            pipeline_run.status = PipelineRunStatus.COMPLETED
            pipeline_run.completed_at = datetime.now(UTC)
            pipeline_run.config_hash = _config_hash(
                sample_fps=effective_sample_fps, threshold=settings.detection_threshold
            )

        log.info(
            "run_video_detection_completed",
            frames_processed=len(frame_paths),
            model_version=model_version,
        )
        return {
            "status": "completed",
            "pipeline_run_id": pipeline_run_id,
            "frames_processed": len(frame_paths),
        }

    except httpx.ConnectError as exc:
        # The most common, entirely expected failure mode for a local-only
        # dependency the operator starts manually -- must never be
        # confused with a genuine bug. Retried (the operator may just not
        # have started it yet) but with a clear, actionable error message,
        # never a silently empty/fabricated detection result.
        log.warning("run_video_detection_inference_server_unreachable", error=str(exc))
        with session_scope() as db:
            pipeline_run = db.get(PipelineRun, pipeline_run_id)
            if pipeline_run:
                pipeline_run.status = PipelineRunStatus.FAILED
                pipeline_run.error = (
                    f"Local inference server unreachable at "
                    f"{settings.detection_inference_url} -- start it with `uv run --project ml "
                    f"--extra inference --extra server uvicorn volley_ml.detection.server:app "
                    f"--host 0.0.0.0 --port 8500` (see that module's docstring)."
                )
        raise self.retry(exc=exc) from exc
    except Exception as exc:
        log.exception("run_video_detection_failed")
        with session_scope() as db:
            pipeline_run = db.get(PipelineRun, pipeline_run_id)
            if pipeline_run:
                pipeline_run.status = PipelineRunStatus.FAILED
                pipeline_run.error = str(exc)
        raise self.retry(exc=exc) from exc
