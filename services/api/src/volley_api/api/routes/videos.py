"""Video ingest endpoints (Phase 4) -- see docs/architecture/DATA_FLOW.md's
upload lifecycle. Every query is scoped to `principal.organization_id`,
exactly like matches.py/ontology.py.

Flow:
1. POST /videos -> creates a `Video` row (video_hash still null -- see
   ontology.py's docstring on that column) + a `VideoAsset(kind=ORIGINAL)`
   row reserving the storage key, and returns a signed upload target.
2. Browser PUTs the raw bytes directly to that target (local dev: a route
   on this same API, see the local-upload route below; production: R2,
   bypassing this API entirely -- see StorageAdapter).
3. POST /videos/{id}/complete-upload -> enqueues the `ingest_video` Celery
   task (SHA-256 + ffprobe + persist), matching the idempotent-enqueue
   pattern matches.py's demo-process trigger already uses.
4. GET /videos/{id} -> poll `status` (uploaded -> validating -> ready/failed).
"""

import asyncio
import re
import tempfile
from pathlib import Path

import numpy as np
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from volley_domain.base import utcnow
from volley_domain.models import Match
from volley_domain.ontology import (
    CameraSegment,
    CourtCalibration,
    HomographyMethod,
    ModelRun,
    ModelRunStage,
    PipelineRun,
    PipelineRunStatus,
    ShotType,
    TacticalUsability,
    Video,
    VideoAsset,
    VideoAssetKind,
    VideoDetectionFrame,
    VideoStatus,
)
from volley_domain.schemas import (
    BallDetectionBoxOut,
    CourtCalibrationOut,
    CourtCalibrationPreviewRequest,
    CourtCalibrationPreviewResponse,
    CourtKeypointIn,
    CreateCourtCalibrationRequest,
    DetectionBoxOut,
    DownloadTargetOut,
    PipelineRunStatusOut,
    TriggerDetectionRequest,
    TriggerDetectionResponse,
    UploadTargetOut,
    VideoDetectionFrameOut,
    VideoDetectionStatusOut,
    VideoOut,
    VideoPlaybackResponse,
    VideoUploadRequest,
    VideoUploadResponse,
)
from volley_domain.tasks import DETECTION_PIPELINE_VERSION
from volley_ml.court.geometry import estimate_homography, homography_reprojection_errors
from volley_ml.court.keypoints import COURT_KEYPOINT_WORLD_POSITIONS_M

from volley_api.core.auth import Principal, get_current_principal, require_org_roles
from volley_api.core.config import get_settings
from volley_api.core.db import get_db
from volley_api.core.storage import get_storage_adapter
from volley_api.core.tasks import enqueue_ingest_video, enqueue_run_video_detection

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["videos"])

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(filename: str) -> str:
    # Storage keys are constructed from this -- must never allow a path
    # separator or ".." through, even though LocalFilesystemStorageAdapter
    # also independently rejects unsafe keys (defense in depth, not a
    # substitute for that check).
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    name = _UNSAFE_FILENAME_CHARS.sub("_", name)
    return name or "upload.bin"


async def _get_org_scoped_video(video_id: str, principal: Principal, db: AsyncSession) -> Video:
    result = await db.execute(
        select(Video).where(
            Video.id == video_id, Video.organization_id == principal.organization_id
        )
    )
    video = result.scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return video


@router.post("/videos", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def create_video_upload(
    body: VideoUploadRequest,
    principal: Principal = Depends(require_org_roles("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> VideoUploadResponse:
    settings = get_settings()
    if body.size_bytes is not None and body.size_bytes > settings.max_video_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Video exceeds the upload limit of {settings.max_video_upload_bytes} bytes",
        )
    if body.match_id is not None:
        match_result = await db.execute(
            select(Match).where(
                Match.id == body.match_id, Match.organization_id == principal.organization_id
            )
        )
        if match_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="match_id not found for this org"
            )

    video = Video(
        organization_id=principal.organization_id,
        match_id=body.match_id,
        filename=body.filename,
        uploaded_by_user_id=principal.user_id,
        status=VideoStatus.UPLOADED,
    )
    db.add(video)
    await db.flush()  # need video.id before building the storage key

    storage_key = (
        f"{principal.organization_id}/videos/{video.id}/original/{_safe_filename(body.filename)}"
    )
    db.add(VideoAsset(video_id=video.id, kind=VideoAssetKind.ORIGINAL, storage_ref=storage_key))
    await db.commit()

    adapter = get_storage_adapter()
    target = adapter.create_signed_upload(storage_key, content_type=body.content_type)

    logger.info("video_upload_url_issued", video_id=video.id, storage_key=storage_key)
    return VideoUploadResponse(
        video_id=video.id,
        upload=UploadTargetOut(
            url=target.url,
            method="PUT",
            headers=target.headers,
            expires_at=target.expires_at,
        ),
    )


@router.put("/storage/local-upload/{key:path}")
async def local_upload(key: str, request: Request, token: str, expires_at: str) -> Response:
    """The local-dev stand-in for a real signed R2 PUT URL -- see
    volley_storage.local.LocalFilesystemStorageAdapter's module docstring.
    Never reachable in production (STORAGE_BACKEND=r2 there, so
    create_video_upload never issues a URL pointing here, and
    Settings._local_storage_cannot_reach_production refuses to even start
    with STORAGE_BACKEND=local outside dev/test).

    Not a scalability claim for real multi-GB uploads -- production traffic
    never hits this route at all: R2's real presigned PUT goes directly
    from the browser to R2, per DATA_FLOW.md's "video bytes never transit
    FastAPI" rule. This route is the one deliberate, documented exception
    to that rule, scoped to local dev only.
    """
    from datetime import datetime

    from volley_storage.local import LocalFilesystemStorageAdapter, SignedUrlError

    adapter = get_storage_adapter()
    if not isinstance(adapter, LocalFilesystemStorageAdapter):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local upload endpoint is only active when STORAGE_BACKEND=local",
        )

    try:
        parsed_expires_at = datetime.fromisoformat(expires_at)
        adapter.verify_upload_token(key, token, parsed_expires_at)
    except (SignedUrlError, ValueError, TypeError) as exc:
        # TypeError: datetime.fromisoformat can yield a naive datetime,
        # which raises TypeError (not ValueError) when compared against
        # verify_upload_token's own timezone-aware "now" -- an earlier
        # version only caught ValueError, so a malformed-but-parseable
        # expires_at crashed as an unhandled 500 (with a full traceback
        # logged) instead of a clean 403, and needed no valid token at all
        # to trigger. Caught by independent security review.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    # First-write-wins: refuse to overwrite an object that already exists
    # at this key. Without this, the same (key, token) pair -- valid for
    # its full expiry window, since the token isn't marked consumed -- can
    # be replayed with different bytes after ingest has already hashed the
    # first upload, silently detaching video_hash from what's actually
    # stored. Caught by independent security review (demonstrated live: a
    # second PUT with different content succeeded after the first had
    # already been hashed).
    if await asyncio.to_thread(adapter.object_exists, key):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An object already exists at this key -- uploads are write-once",
        )

    settings = get_settings()
    upload_limit = min(settings.local_upload_max_bytes, settings.max_video_upload_bytes)
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > upload_limit:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"Upload exceeds the local-dev limit of {upload_limit} bytes",
                )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Content-Length header"
            ) from exc

    total = 0
    try:
        # Spool to disk after 8 MiB so a local-dev upload never accumulates
        # the whole match in process memory. Production uploads bypass the
        # API entirely and go straight to R2.
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as spool:
            async for chunk in request.stream():
                total += len(chunk)
                if total > upload_limit:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"Upload exceeds the local-dev limit of {upload_limit} bytes",
                    )
                spool.write(chunk)
            spool.seek(0)

            def _chunks():
                while data := spool.read(8 * 1024 * 1024):
                    yield data

            written = await asyncio.to_thread(adapter.write_object, key, _chunks())
    except ValueError as exc:
        # write_object's own key-safety check (path traversal etc.) raises
        # ValueError -- an earlier version let this escape as an unhandled
        # 500 instead of a clean 403 (the key was already accepted by the
        # route's path parameter before this validation ever ran). Caught
        # by independent security review.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    logger.info("local_upload_written", key=key, bytes=written)
    return Response(status_code=status.HTTP_200_OK)


@router.post("/videos/{video_id}/complete-upload", response_model=VideoOut)
async def complete_video_upload(
    video_id: str,
    principal: Principal = Depends(require_org_roles("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> Video:
    video = await _get_org_scoped_video(video_id, principal, db)

    if video.status in (VideoStatus.VALIDATING, VideoStatus.READY):
        # Idempotent: already in flight or already done -- never
        # double-enqueue, same rule as matches.py's demo-process trigger.
        return video

    asset_result = await db.execute(
        select(VideoAsset).where(
            VideoAsset.video_id == video_id, VideoAsset.kind == VideoAssetKind.ORIGINAL
        )
    )
    asset = asset_result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No original storage reference found for this video",
        )

    # The client hasn't necessarily actually uploaded anything yet -- an
    # earlier version flipped straight to VALIDATING and enqueued
    # regardless, so calling this before the PUT completed queued a task
    # that would always fail ffprobe/hashing against a missing object.
    # Caught by independent security review.
    adapter = get_storage_adapter()
    if not await asyncio.to_thread(adapter.object_exists, asset.storage_ref):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No object has been uploaded to this video's storage key yet",
        )

    metadata = await asyncio.to_thread(adapter.stat, asset.storage_ref)
    max_bytes = get_settings().max_video_upload_bytes
    if metadata.size_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The uploaded video object is empty",
        )
    if metadata.size_bytes > max_bytes:
        video.status = VideoStatus.FAILED
        video.error = f"Uploaded object exceeds the configured limit of {max_bytes} bytes"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=video.error,
        )

    video.status = VideoStatus.VALIDATING
    video.error = None
    await db.commit()
    await db.refresh(video)

    try:
        await asyncio.to_thread(
            enqueue_ingest_video, video_id=video.id, storage_key=asset.storage_ref
        )
    except Exception as exc:
        # If the status flip above committed but enqueueing then fails
        # (e.g. Valkey unreachable), the row was left stuck in VALIDATING
        # forever: VALIDATING is one of the two idempotency-guard statuses
        # at the top of this function, so a client retry would silently
        # short-circuit into "already in flight" and never actually
        # re-enqueue. Revert to FAILED (not in that guard tuple) so a
        # retry genuinely retries. Caught by independent architecture
        # review.
        logger.exception("ingest_video_enqueue_failed", video_id=video.id)
        video.status = VideoStatus.FAILED
        video.error = f"Failed to enqueue ingest task: {exc}"
        await db.commit()
        await db.refresh(video)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not enqueue ingest task -- please retry",
        ) from exc

    logger.info("ingest_video_enqueued", video_id=video.id, storage_key=asset.storage_ref)
    return video


@router.get("/videos/{video_id}", response_model=VideoOut)
async def get_video(
    video_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Video:
    return await _get_org_scoped_video(video_id, principal, db)


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    video_id: str,
    principal: Principal = Depends(require_org_roles("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Permanently deletes a video: every `VideoAsset`/`PipelineRun`/
    `ModelRun`/`VideoDetectionFrame` row cascades at the DB level (all
    already `ondelete="CASCADE"` from `videos.id` -- see ontology.py), and
    every real object this video ever wrote to storage (original + any
    proxy/clip assets) is deleted too, not just the DB row -- otherwise the
    actual video bytes silently outlive every reference to them. A video
    linked to a `Match` only has that link cleared (`ondelete="SET NULL"`)
    -- deleting a video never deletes the match it was attached to.
    """
    video = await _get_org_scoped_video(video_id, principal, db)

    assets_result = await db.execute(select(VideoAsset).where(VideoAsset.video_id == video_id))
    assets = list(assets_result.scalars().all())

    adapter = get_storage_adapter()
    for asset in assets:
        try:
            await asyncio.to_thread(adapter.delete, asset.storage_ref)
        except Exception:
            # Storage deletion is best-effort: the DB row is the source of
            # truth for "does this video still exist to this org," and a
            # storage-layer hiccup (network blip, R2 transient error) must
            # not block that from happening -- an orphaned object with no
            # DB row pointing at it is a cheap, silent cleanup problem, not
            # a correctness one. Logged loudly so it isn't invisible.
            logger.exception(
                "video_delete_storage_object_failed",
                video_id=video_id,
                storage_ref=asset.storage_ref,
            )

    await db.delete(video)
    await db.commit()

    logger.info("video_deleted", video_id=video_id, organization_id=principal.organization_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/videos", response_model=list[VideoOut])
async def list_videos(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[Video]:
    result = await db.execute(
        select(Video)
        .where(Video.organization_id == principal.organization_id)
        .order_by(Video.uploaded_at.desc())
    )
    return list(result.scalars().all())


@router.get("/videos/{video_id}/playback-url", response_model=VideoPlaybackResponse)
async def get_video_playback_url(
    video_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> VideoPlaybackResponse:
    """Issues a short-lived signed GET target for a <video> element's
    `src` -- the read-side counterpart of POST /videos' signed upload,
    same "bytes never transit FastAPI" rule (DATA_FLOW.md). Requires a
    real JWT-authenticated, org-scoped principal (unlike the local-upload/
    local-download routes below, which are authorized purely by their own
    signed token, matching how a real presigned URL works) -- this route
    is what *hands out* that token in the first place, so it's the actual
    access-control checkpoint.
    """
    video = await _get_org_scoped_video(video_id, principal, db)
    if video.status != VideoStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Video is not ready for playback (status={video.status.value})",
        )

    asset_result = await db.execute(
        select(VideoAsset).where(
            VideoAsset.video_id == video_id, VideoAsset.kind == VideoAssetKind.ORIGINAL
        )
    )
    asset = asset_result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No original storage reference found for this video",
        )

    adapter = get_storage_adapter()
    target = await asyncio.to_thread(adapter.create_signed_download, asset.storage_ref)
    return VideoPlaybackResponse(
        video_id=video.id,
        playback=DownloadTargetOut(url=target.url, expires_at=target.expires_at),
    )


async def _latest_detection_pipeline_run(video_id: str, db: AsyncSession) -> PipelineRun | None:
    result = await db.execute(
        select(PipelineRun)
        .where(
            PipelineRun.video_id == video_id,
            PipelineRun.pipeline_version == DETECTION_PIPELINE_VERSION,
        )
        .order_by(PipelineRun.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.post("/videos/{video_id}/detect", response_model=TriggerDetectionResponse)
async def trigger_video_detection(
    video_id: str,
    body: TriggerDetectionRequest | None = None,
    principal: Principal = Depends(require_org_roles("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> TriggerDetectionResponse:
    """Enqueues the exploratory RF-DETR detection pipeline (see
    volley_worker.detection) for a real uploaded video. Idempotent per the
    same rule matches.py's demo-process trigger and complete_video_upload
    already use: a QUEUED/RUNNING/COMPLETED run for this video is reused,
    never double-enqueued; a FAILED run gets a fresh PipelineRun row (see
    PipelineRun's own "one execution" docstring -- unlike ProcessingJob, a
    retry here is a new row, not a mutated one). An optional body lets the
    caller cap processing to the video's own first `max_duration_seconds`
    -- ignored when an existing run is reused below, matching how every
    other field of a reused run reflects the *original* trigger, not the
    new request. `start_offset_seconds` similarly lets the caller skip a
    real match's warmup/pre-play footage and start analysis from the
    moment play actually begins (see extract_frames_at_fps's docstring).
    `sample_fps` overrides the worker's env-configured detection rate for
    this one run.
    """
    video = await _get_org_scoped_video(video_id, principal, db)
    if video.status != VideoStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Video is not ready for detection (status={video.status.value})",
        )

    existing = await _latest_detection_pipeline_run(video_id, db)
    if existing is not None and existing.status in (
        PipelineRunStatus.QUEUED,
        PipelineRunStatus.RUNNING,
        PipelineRunStatus.COMPLETED,
    ):
        logger.info(
            "video_detection_reused_existing_run",
            video_id=video_id,
            pipeline_run_id=existing.id,
            status=existing.status,
        )
        return TriggerDetectionResponse(
            pipeline_run_id=existing.id, status=PipelineRunStatusOut(existing.status.value)
        )

    pipeline_run = PipelineRun(
        video_id=video_id,
        pipeline_version=DETECTION_PIPELINE_VERSION,
        # Placeholder -- sample_fps/threshold are worker-side runtime
        # settings this route has no authoritative view of; the worker
        # overwrites this with the real value once it knows what it ran
        # with (see volley_worker.detection._config_hash's docstring).
        config_hash="pending",
        status=PipelineRunStatus.QUEUED,
    )
    db.add(pipeline_run)
    await db.commit()
    await db.refresh(pipeline_run)

    try:
        await asyncio.to_thread(
            enqueue_run_video_detection,
            pipeline_run_id=pipeline_run.id,
            video_id=video_id,
            max_duration_seconds=body.max_duration_seconds if body else None,
            start_offset_seconds=body.start_offset_seconds if body else None,
            sample_fps=body.sample_fps if body else None,
        )
    except Exception as exc:
        logger.exception("video_detection_enqueue_failed", video_id=video_id)
        pipeline_run.status = PipelineRunStatus.FAILED
        pipeline_run.error = f"Failed to enqueue detection task: {exc}"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not enqueue detection task -- please retry",
        ) from exc

    logger.info("video_detection_enqueued", video_id=video_id, pipeline_run_id=pipeline_run.id)
    return TriggerDetectionResponse(
        pipeline_run_id=pipeline_run.id, status=PipelineRunStatusOut(pipeline_run.status.value)
    )


@router.get("/videos/{video_id}/detection-status", response_model=VideoDetectionStatusOut)
async def get_video_detection_status(
    video_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> VideoDetectionStatusOut:
    """Polled by the frontend after POST .../detect. Returns an honest
    all-None/zero shape when no detection run has ever been triggered for
    this video -- never a fabricated empty result (CLAUDE.md's abstention
    principle)."""
    await _get_org_scoped_video(video_id, principal, db)

    pipeline_run = await _latest_detection_pipeline_run(video_id, db)
    if pipeline_run is None:
        return VideoDetectionStatusOut(
            pipeline_run_id=None,
            status=None,
            model_version=None,
            sample_fps=None,
            frames_detected=0,
            frames_total=None,
            error=None,
        )

    model_run_result = await db.execute(
        select(ModelRun).where(
            ModelRun.pipeline_run_id == pipeline_run.id, ModelRun.stage == ModelRunStage.DETECTION
        )
    )
    model_run = model_run_result.scalar_one_or_none()

    frames_detected = 0
    if model_run is not None:
        count_result = await db.execute(
            select(VideoDetectionFrame).where(VideoDetectionFrame.model_run_id == model_run.id)
        )
        frames_detected = len(count_result.scalars().all())

    return VideoDetectionStatusOut(
        pipeline_run_id=pipeline_run.id,
        status=PipelineRunStatusOut(pipeline_run.status.value),
        model_version=model_run.model_version if model_run else None,
        # "base_sample_fps" -- the baseline rate the worker's own burst
        # re-sampling phase may locally exceed around a real ball sighting
        # (see volley_worker.detection's docstring); this status field
        # reports the baseline, not a fabricated blended average.
        sample_fps=(model_run.metrics or {}).get("base_sample_fps") if model_run else None,
        frames_detected=frames_detected,
        frames_total=(model_run.metrics or {}).get("frames_total") if model_run else None,
        error=pipeline_run.error,
    )


@router.get("/videos/{video_id}/detections", response_model=list[VideoDetectionFrameOut])
async def list_video_detections(
    video_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[VideoDetectionFrameOut]:
    """Returns the latest COMPLETED detection run's per-frame boxes, in
    frame order. An empty list covers both "never analyzed" and "analysis
    still running" -- callers should check detection-status first to tell
    those apart, exactly like the video library already treats an empty
    `duration_seconds` as "probe pending", not "zero-length video".
    """
    await _get_org_scoped_video(video_id, principal, db)

    pipeline_run = await _latest_detection_pipeline_run(video_id, db)
    if pipeline_run is None or pipeline_run.status != PipelineRunStatus.COMPLETED:
        return []

    model_run_result = await db.execute(
        select(ModelRun).where(
            ModelRun.pipeline_run_id == pipeline_run.id, ModelRun.stage == ModelRunStage.DETECTION
        )
    )
    model_run = model_run_result.scalar_one_or_none()
    if model_run is None:
        return []

    frames_result = await db.execute(
        select(VideoDetectionFrame)
        .where(VideoDetectionFrame.model_run_id == model_run.id)
        .order_by(VideoDetectionFrame.frame_index)
    )
    frames = frames_result.scalars().all()
    return [
        VideoDetectionFrameOut(
            frame_index=frame.frame_index,
            timestamp_seconds=frame.timestamp_seconds,
            detections=[DetectionBoxOut(**box) for box in frame.detections],
            balls=[BallDetectionBoxOut(**ball) for ball in frame.ball_detections],
        )
        for frame in frames
    ]


def _visible_keypoint_correspondences(
    keypoints: list[CourtKeypointIn],
) -> tuple[np.ndarray, np.ndarray]:
    visible = [k for k in keypoints if k.visible]
    source_xy = np.array([(k.x_pixel, k.y_pixel) for k in visible], dtype=np.float64)
    target_xy = np.array(
        [COURT_KEYPOINT_WORLD_POSITIONS_M[k.keypoint_name] for k in visible], dtype=np.float64
    )
    return source_xy, target_xy


@router.post(
    "/videos/{video_id}/court-calibration/preview", response_model=CourtCalibrationPreviewResponse
)
async def preview_court_calibration(
    video_id: str,
    body: CourtCalibrationPreviewRequest,
    principal: Principal = Depends(require_org_roles("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> CourtCalibrationPreviewResponse:
    """Debounced live-feedback endpoint for the manual calibration UI --
    computes reprojection error for the in-progress keypoint set without
    persisting anything, so a human sees calibration quality *while*
    clicking, not only after submitting. Calls the exact same ml/court/
    geometry functions the real persisting route below does (never a
    second, divergent estimator), so the live number and the saved number
    can never disagree."""
    await _get_org_scoped_video(video_id, principal, db)
    source_xy, target_xy = _visible_keypoint_correspondences(body.keypoints)
    try:
        homography = estimate_homography(source_xy, target_xy)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    errors = homography_reprojection_errors(source_xy, target_xy, homography)
    return CourtCalibrationPreviewResponse(reprojection_error_px=float(np.mean(errors)))


@router.post(
    "/videos/{video_id}/court-calibration",
    response_model=CourtCalibrationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_court_calibration(
    video_id: str,
    body: CreateCourtCalibrationRequest,
    principal: Principal = Depends(require_org_roles("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> CourtCalibration:
    """Manual calibration only (CLAUDE.md: "a correct manual calibration
    beats a false automatic one") -- no auto-detection path exists yet.

    Creates exactly one CameraSegment per video if none exists yet -- a
    deliberate MVP simplification: no shot-boundary/camera-cut detection
    pipeline exists, so this assumes one camera framing for the whole
    video. Surfaced to the user as a persistent warning in the calibration
    UI, never silently assumed away. An existing unsuperseded calibration
    on that segment is superseded, never overwritten in place or deleted
    -- see CourtCalibration's own docstring on why."""
    video = await _get_org_scoped_video(video_id, principal, db)
    if video.status != VideoStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Video is not ready for calibration (status={video.status.value})",
        )

    segment_result = await db.execute(
        select(CameraSegment)
        .where(CameraSegment.video_id == video.id)
        .order_by(CameraSegment.index_in_video)
    )
    segment = segment_result.scalars().first()
    if segment is None:
        segment = CameraSegment(
            video_id=video.id,
            index_in_video=0,
            video_t_start=0.0,
            video_t_end=None,
            shot_type=ShotType(body.camera_shot_type.value),
            tactical_usable=TacticalUsability(body.camera_tactical_usable.value),
        )
        db.add(segment)
        await db.flush()

    source_xy, target_xy = _visible_keypoint_correspondences(body.keypoints)
    try:
        homography = estimate_homography(source_xy, target_xy)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    errors = homography_reprojection_errors(source_xy, target_xy, homography)

    existing_result = await db.execute(
        select(CourtCalibration).where(
            CourtCalibration.camera_segment_id == segment.id,
            CourtCalibration.superseded_at.is_(None),
        )
    )
    for existing in existing_result.scalars().all():
        existing.superseded_at = utcnow()

    calibration = CourtCalibration(
        camera_segment_id=segment.id,
        method=HomographyMethod.MANUAL,
        image_width=body.image_width,
        image_height=body.image_height,
        homography_matrix=homography.flatten().tolist(),
        keypoints=[k.model_dump() for k in body.keypoints],
        net_height_m=body.net_height_m,
        court_width_m=body.court_width_m,
        court_length_m=body.court_length_m,
        zone_mirror_x=body.zone_mirror_x,
        reprojection_error_px=float(np.mean(errors)),
        confidence=None,
        created_by_user_id=principal.user_id,
        supports_metric_3d=False,
        camera_matrix=None,
        rotation_world_to_camera=None,
        translation_world_to_camera_m=None,
    )
    db.add(calibration)
    await db.commit()
    await db.refresh(calibration)
    logger.info(
        "court_calibration_created",
        video_id=video_id,
        camera_segment_id=segment.id,
        reprojection_error_px=calibration.reprojection_error_px,
    )
    return calibration


@router.get("/videos/{video_id}/court-calibration", response_model=CourtCalibrationOut | None)
async def get_court_calibration(
    video_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> CourtCalibration | None:
    """Current (non-superseded) calibration for this video, or None if one
    has never been created -- an honest empty state, never a fabricated
    placeholder, matching get_video_detection_status's own pattern."""
    video = await _get_org_scoped_video(video_id, principal, db)
    result = await db.execute(
        select(CourtCalibration)
        .join(CameraSegment, CourtCalibration.camera_segment_id == CameraSegment.id)
        .where(CameraSegment.video_id == video.id, CourtCalibration.superseded_at.is_(None))
        .order_by(CourtCalibration.created_at.desc())
    )
    return result.scalars().first()


@router.get("/storage/local-download/{key:path}")
async def local_download(key: str, token: str, expires_at: str) -> Response:
    """The local-dev stand-in for a real signed R2 GET URL -- the read-side
    mirror of local_upload above. Never reachable in production for the
    same reasons local_upload isn't (STORAGE_BACKEND=r2 there; a real R2
    presigned GET streams the browser <video> element directly from R2,
    never through this API).

    Authorized purely by the signed `token` (which encodes "download",
    distinct from an "upload" token for the same key -- see
    LocalFilesystemStorageAdapter._token_for's docstring), not a JWT --
    this matches exactly how a real presigned URL works: whoever holds the
    URL can fetch it, no separate bearer auth required, for the token's
    limited lifetime.
    """
    from datetime import datetime

    from fastapi.responses import FileResponse
    from volley_storage.local import LocalFilesystemStorageAdapter, SignedUrlError

    adapter = get_storage_adapter()
    if not isinstance(adapter, LocalFilesystemStorageAdapter):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local download endpoint is only active when STORAGE_BACKEND=local",
        )

    try:
        parsed_expires_at = datetime.fromisoformat(expires_at)
        adapter.verify_download_token(key, token, parsed_expires_at)
    except (SignedUrlError, ValueError, TypeError) as exc:
        # Same TypeError caveat as local_upload's own try/except -- a
        # malformed-but-parseable expires_at yields a naive datetime,
        # which raises TypeError (not ValueError) when compared against
        # verify_download_token's timezone-aware "now".
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    try:
        # `destination` is a required Path arg but, per
        # LocalFilesystemStorageAdapter.download_to_path's own docstring,
        # is ignored for the local backend -- it returns the object's real
        # on-disk path directly rather than copying a potentially multi-GB
        # video. Passed here only to satisfy the StorageAdapter interface.
        path = await asyncio.to_thread(
            adapter.download_to_path, key, Path("/unused/local-download-destination")
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:  # StorageObjectNotFoundError, kept generic to avoid an import cycle
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    # FileResponse handles Range requests natively (verified against the
    # installed Starlette version, not assumed) -- required for real
    # <video> seeking to work, not just full-file playback.
    return FileResponse(path, filename=path.name)
