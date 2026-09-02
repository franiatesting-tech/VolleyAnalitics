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

from volley_worker.ball_filtering import compute_burst_windows, find_static_false_positive_ids
from volley_worker.celery_app import celery_app
from volley_worker.config import Settings, get_settings
from volley_worker.db import session_scope
from volley_worker.frame_extraction import FrameExtractionFailedError, extract_frames_at_fps
from volley_worker.storage import get_storage_adapter

logger = structlog.get_logger(__name__)

# Generous relative to RFDETR_NANO_SMOKE.md's observed ~0.4-1.7s/frame on
# CPU -- covers a slower real frame or transient host contention without
# masking a genuinely hung inference server behind an over-long wait.
_HEALTH_CHECK_TIMEOUT_SECONDS = 120.0
_PER_FRAME_TIMEOUT_SECONDS = 30.0


def _config_hash(
    *, sample_fps: float, threshold: float, far_tiling_enabled: bool, burst_enabled: bool
) -> str:
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
            "far_tiling_enabled": far_tiling_enabled,
            "burst_enabled": burst_enabled,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _run_frame_batch(
    client: httpx.Client,
    settings: Settings,
    video_id: str,
    model_run_id: str,
    frame_paths: list[Path],
    *,
    starting_frame_index: int,
    fps: float,
    base_timestamp_seconds: float,
    enable_far_tiling: bool,
) -> tuple[list[tuple[float, dict]], int, int, int]:
    """Runs one batch of already-extracted frames through the inference
    server and commits a VideoDetectionFrame row per frame -- shared by the
    baseline pass and every burst-resampling window (see
    run_video_detection's own docstring) so the bbox-normalization/commit
    logic can't drift between call sites. `base_timestamp_seconds` is the
    absolute video position of this batch's first frame; `starting_frame_index`
    is the frame_index to use for that same frame -- both are chosen by the
    caller so consecutive batches never collide on the
    (model_run_id, frame_index) unique constraint and every stored
    timestamp always means "seconds into the original video."

    Returns (this batch's (timestamp, ball_detection) pairs, person
    candidates found, ball candidates found, candidates vetoed as a shoe).
    """
    person_candidates = 0
    ball_candidates = 0
    vetoed_count = 0
    ball_detections_with_timestamp: list[tuple[float, dict]] = []

    for local_ordinal, frame_path in enumerate(frame_paths):
        frame_index = starting_frame_index + local_ordinal
        timestamp_seconds = base_timestamp_seconds + local_ordinal / fps
        with frame_path.open("rb") as source_file:
            response = client.post(
                f"{settings.detection_inference_url}/detect-frame",
                files={"image": (frame_path.name, source_file, "image/jpeg")},
                data={
                    "threshold": str(settings.detection_threshold),
                    "ball_threshold": str(settings.detection_ball_threshold),
                    "enable_far_tiling": str(enable_far_tiling),
                },
            )
        response.raise_for_status()
        payload = response.json()
        width, height = payload["image_width"], payload["image_height"]
        detections = [
            {
                "candidate_id": f"{video_id}:{frame_index}:{index}",
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
        # At most one ball reading per frame -- verified directly against
        # real match footage that ~46% of frames with any ball detection
        # had multiple simultaneous candidates, mostly harmless
        # near-duplicate boxes around one real object, but with no
        # principled way downstream to choose among them.
        best_ball = max(payload["balls"], key=lambda b: b["confidence"], default=None)
        ball_detections = (
            [
                {
                    "candidate_id": f"{video_id}:{frame_index}:ball:0",
                    "bbox": {
                        "x": best_ball["x1"] / width,
                        "y": best_ball["y1"] / height,
                        "width": (best_ball["x2"] - best_ball["x1"]) / width,
                        "height": (best_ball["y2"] - best_ball["y1"]) / height,
                    },
                    "confidence": best_ball["confidence"],
                    # Overwritten below, once every frame across both the
                    # baseline and burst passes has been persisted and the
                    # full-video static-position filter can see the whole
                    # picture -- see find_static_false_positive_ids's
                    # docstring.
                    "is_static_false_positive": False,
                }
            ]
            if best_ball is not None
            else []
        )
        person_candidates += len(detections)
        ball_candidates += len(ball_detections)
        vetoed_count += payload.get("ball_candidates_vetoed_by_foot_overlap", 0)
        ball_detections_with_timestamp.extend((timestamp_seconds, ball) for ball in ball_detections)

        with session_scope() as db:
            db.add(
                VideoDetectionFrame(
                    video_id=video_id,
                    model_run_id=model_run_id,
                    frame_index=frame_index,
                    timestamp_seconds=timestamp_seconds,
                    detections=detections,
                    ball_detections=ball_detections,
                )
            )

    return ball_detections_with_timestamp, person_candidates, ball_candidates, vetoed_count


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
                        "base_sample_fps": effective_sample_fps,
                        "threshold": settings.detection_threshold,
                        "ball_threshold": settings.detection_ball_threshold,
                        "max_duration_seconds": max_duration_seconds,
                        "start_offset_seconds": start_offset_seconds,
                        "far_tiling_enabled": settings.detection_far_tiling_enabled,
                        "burst_enabled": settings.detection_burst_enabled,
                        "frames_total": len(frame_paths),
                    },
                )
                db.add(model_run)
                db.flush()
                model_run_id = model_run.id

            # Position within the *extracted* clip, plus the skipped prefix
            # added back -- the frontend syncs these timestamps against the
            # real, untrimmed video's own <video>.currentTime, so a stored
            # timestamp must always mean "seconds into the original video,"
            # never "seconds into whatever ffmpeg happened to extract."
            with httpx.Client(timeout=_PER_FRAME_TIMEOUT_SECONDS) as client:
                all_ball_detections, person_candidates, ball_candidates, vetoed_count = (
                    _run_frame_batch(
                        client,
                        settings,
                        video_id,
                        model_run_id,
                        frame_paths,
                        starting_frame_index=1,
                        fps=effective_sample_fps,
                        base_timestamp_seconds=start_offset_seconds or 0.0,
                        enable_far_tiling=settings.detection_far_tiling_enabled,
                    )
                )
                next_frame_index = len(frame_paths) + 1

                burst_windows_count = 0
                burst_windows_dropped = 0
                burst_frames_added = 0
                if settings.detection_burst_enabled:
                    # A static false positive is a fixed scene object, never
                    # a real fast-moving ball -- it must never trigger a
                    # burst window. This provisional pass looks only at
                    # what the baseline pass itself found; the real, final
                    # static-false-positive flag (after this whole block)
                    # is recomputed once more over the combined
                    # baseline+burst data, since a burst-added detection
                    # near the same static spot must be flagged too.
                    provisional_static_ids = find_static_false_positive_ids(all_ball_detections)
                    real_ball_timestamps = [
                        ts
                        for ts, ball in all_ball_detections
                        if ball["candidate_id"] not in provisional_static_ids
                    ]
                    burst_windows, burst_windows_dropped = compute_burst_windows(
                        real_ball_timestamps,
                        window_radius_seconds=settings.detection_burst_window_radius_seconds,
                        max_windows=settings.detection_burst_max_windows,
                    )
                    burst_windows_count = len(burst_windows)

                    if burst_windows:
                        burst_frame_paths_by_window = [
                            extract_frames_at_fps(
                                local_video,
                                tmp_path / f"burst_{window_index}",
                                fps=settings.detection_burst_fps,
                                start_offset_seconds=window_start,
                                max_duration_seconds=window_end - window_start,
                            )
                            for window_index, (window_start, window_end) in enumerate(burst_windows)
                        ]
                        burst_frames_added = sum(len(fp) for fp in burst_frame_paths_by_window)

                        # frames_total is the API's live progress-bar
                        # denominator (see VideoDetectionStatusOut) --
                        # updated before any burst frame starts committing,
                        # or a polling client's progress bar undercounts
                        # for the whole burst phase.
                        with session_scope() as db:
                            refreshed_model_run = db.get(ModelRun, model_run_id)
                            if refreshed_model_run is not None:
                                refreshed_model_run.metrics = {
                                    **(refreshed_model_run.metrics or {}),
                                    "frames_total": len(frame_paths) + burst_frames_added,
                                }

                        for (window_start, _window_end), window_frames in zip(
                            burst_windows, burst_frame_paths_by_window, strict=True
                        ):
                            if not window_frames:
                                continue
                            (
                                window_ball_detections,
                                window_person_candidates,
                                window_ball_candidates,
                                window_vetoed_count,
                            ) = _run_frame_batch(
                                client,
                                settings,
                                video_id,
                                model_run_id,
                                window_frames,
                                starting_frame_index=next_frame_index,
                                fps=settings.detection_burst_fps,
                                base_timestamp_seconds=window_start,
                                enable_far_tiling=settings.detection_far_tiling_enabled,
                            )
                            next_frame_index += len(window_frames)
                            all_ball_detections.extend(window_ball_detections)
                            person_candidates += window_person_candidates
                            ball_candidates += window_ball_candidates
                            vetoed_count += window_vetoed_count

        frames_processed = next_frame_index - 1
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
                # module's other per-model_run queries. Covers both the
                # baseline pass and every burst window's rows, since they
                # all share this one model_run_id.
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
                "frames_processed": frames_processed,
                "person_candidates": person_candidates,
                "ball_candidates": ball_candidates,
                "ball_candidates_vetoed_by_foot_overlap": vetoed_count,
                "burst_sample_fps": settings.detection_burst_fps,
                "burst_windows_count": burst_windows_count,
                "burst_windows_dropped": burst_windows_dropped,
                "burst_frames_added": burst_frames_added,
            }

            pipeline_run.status = PipelineRunStatus.COMPLETED
            pipeline_run.completed_at = datetime.now(UTC)
            pipeline_run.config_hash = _config_hash(
                sample_fps=effective_sample_fps,
                threshold=settings.detection_threshold,
                far_tiling_enabled=settings.detection_far_tiling_enabled,
                burst_enabled=settings.detection_burst_enabled,
            )

        log.info(
            "run_video_detection_completed",
            frames_processed=frames_processed,
            model_version=model_version,
        )
        return {
            "status": "completed",
            "pipeline_run_id": pipeline_run_id,
            "frames_processed": frames_processed,
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
