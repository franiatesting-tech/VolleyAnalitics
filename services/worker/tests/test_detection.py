"""Tests for the run_video_detection Celery task
(services/worker/src/volley_worker/detection.py). Fully mocked: the local
inference server (httpx calls) and frame extraction (ffmpeg) are both
monkeypatched, matching test_ingest.py's own "fully mocked logic tests"
precedent -- this suite proves the task's own orchestration/persistence
logic (idempotency, provenance, honest failure), not the real ffmpeg/HTTP
plumbing, which would require a running inference server and real ffmpeg
(exercised manually, see volley_ml.detection.server's own docstring).
"""

from pathlib import Path

import httpx
import pytest
from volley_domain.ontology import (
    ModelRun,
    ModelRunStage,
    PipelineRun,
    PipelineRunStatus,
    Video,
    VideoAsset,
    VideoAssetKind,
    VideoDetectionFrame,
    VideoStatus,
)


def _seed_video_with_pipeline_run(
    session_factory, *, video_id="v1", organization_id="org1", pipeline_run_id="pr1"
):
    with session_factory() as db:
        db.add(
            Video(
                id=video_id,
                organization_id=organization_id,
                filename="clip.mp4",
                uploaded_by_user_id="user1",
                status=VideoStatus.READY,
            )
        )
        db.add(
            VideoAsset(
                video_id=video_id,
                kind=VideoAssetKind.ORIGINAL,
                storage_ref=f"{organization_id}/videos/{video_id}/original/clip.mp4",
            )
        )
        db.add(
            PipelineRun(
                id=pipeline_run_id,
                video_id=video_id,
                pipeline_version="video-detection-exploratory-v1",
                config_hash="pending",
                status=PipelineRunStatus.QUEUED,
            )
        )
        db.commit()


class _FakeResponse:
    """Always a 200 in this suite -- an HTTP error status from the
    inference server (as opposed to a connection failure, which is
    exercised separately below) isn't a code path this task branches on
    differently, so raise_for_status is a no-op stub here."""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, *, health_payload, frame_payloads, connect_error=False, fail_after=None):
        self._health_payload = health_payload
        self._frame_payloads = list(frame_payloads)
        self._connect_error = connect_error
        self._fail_after = fail_after
        self._posts_made = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def get(self, url):
        if self._connect_error:
            raise httpx.ConnectError("connection refused", request=None)
        return _FakeResponse(self._health_payload)

    def post(self, url, *, files, data):
        if self._fail_after is not None and self._posts_made >= self._fail_after:
            raise RuntimeError("simulated inference server crash mid-run")
        self._posts_made += 1
        return _FakeResponse(self._frame_payloads.pop(0))


def _make_frame_files(tmp_path: Path, count: int) -> list[Path]:
    paths = []
    for index in range(count):
        path = tmp_path / f"frame_{index:06d}.jpg"
        path.write_bytes(b"fake-jpeg-bytes")
        paths.append(path)
    return paths


def _patch_common(
    monkeypatch,
    *,
    frame_paths,
    health_payload=None,
    frame_payloads=None,
    connect_error=False,
    fail_after=None,
    extract_calls=None,
    fps_calls=None,
):
    import volley_worker.detection as detection_module

    monkeypatch.setattr(detection_module, "get_storage_adapter", lambda: _FakeAdapter())

    def _fake_extract(source, out_dir, fps, max_duration_seconds=None, start_offset_seconds=None):
        if extract_calls is not None:
            extract_calls.append(max_duration_seconds)
        if fps_calls is not None:
            fps_calls.append(fps)
        return frame_paths

    monkeypatch.setattr(detection_module, "extract_frames_at_fps", _fake_extract)

    client = _FakeClient(
        health_payload=health_payload
        or {"status": "ok", "model_version": "rfdetr-nano-test", "weights_sha256": "f" * 64},
        frame_payloads=frame_payloads or [],
        connect_error=connect_error,
        fail_after=fail_after,
    )
    monkeypatch.setattr(detection_module.httpx, "Client", lambda timeout: client)


class _FakeAdapter:
    def download_to_path(self, key, destination):
        return destination


def test_raises_if_pipeline_run_missing(sqlite_session_factory, monkeypatch):
    from volley_worker.detection import run_video_detection

    _patch_common(monkeypatch, frame_paths=[])
    with pytest.raises(ValueError):
        run_video_detection.run(pipeline_run_id="does-not-exist", video_id="v1")


def test_already_completed_is_a_noop(sqlite_session_factory, monkeypatch):
    from volley_worker.detection import run_video_detection

    _seed_video_with_pipeline_run(sqlite_session_factory)
    with sqlite_session_factory() as db:
        db.get(PipelineRun, "pr1").status = PipelineRunStatus.COMPLETED
        db.commit()

    _patch_common(monkeypatch, frame_paths=[])
    result = run_video_detection.run(pipeline_run_id="pr1", video_id="v1")
    assert result["status"] == "already_completed"


def test_success_persists_frames_with_provenance(sqlite_session_factory, monkeypatch, tmp_path):
    from volley_worker.detection import run_video_detection

    _seed_video_with_pipeline_run(sqlite_session_factory)
    frame_paths = _make_frame_files(tmp_path, 2)
    _patch_common(
        monkeypatch,
        frame_paths=frame_paths,
        frame_payloads=[
            {
                "image_width": 100,
                "image_height": 200,
                "boxes": [
                    {
                        "x1": 10,
                        "y1": 20,
                        "x2": 30,
                        "y2": 180,
                        "confidence": 0.9,
                        "jersey_color_outlier": False,
                    }
                ],
                "balls": [
                    {"x1": 40, "y1": 60, "x2": 50, "y2": 70, "confidence": 0.25},
                ],
            },
            {
                "image_width": 100,
                "image_height": 200,
                "boxes": [],
                "balls": [],
            },
        ],
    )

    result = run_video_detection.run(pipeline_run_id="pr1", video_id="v1")
    assert result["status"] == "completed"
    assert result["frames_processed"] == 2

    with sqlite_session_factory() as db:
        pipeline_run = db.get(PipelineRun, "pr1")
        assert pipeline_run.status == PipelineRunStatus.COMPLETED
        assert pipeline_run.config_hash != "pending"
        assert pipeline_run.completed_at is not None

        model_runs = db.query(ModelRun).filter_by(pipeline_run_id="pr1").all()
        assert len(model_runs) == 1
        model_run = model_runs[0]
        assert model_run.stage == ModelRunStage.DETECTION
        assert model_run.model_version == "rfdetr-nano-test"
        assert model_run.weights_hash == "f" * 64
        assert model_run.metrics["frames_processed"] == 2
        assert model_run.metrics["frames_total"] == 2
        assert model_run.metrics["person_candidates"] == 1
        assert model_run.metrics["ball_candidates"] == 1

        frames = (
            db.query(VideoDetectionFrame)
            .filter_by(model_run_id=model_run.id)
            .order_by(VideoDetectionFrame.frame_index)
            .all()
        )
        assert len(frames) == 2
        assert frames[0].frame_index == 1
        assert frames[0].timestamp_seconds == 0.0
        assert len(frames[0].detections) == 1
        box = frames[0].detections[0]
        assert box["confidence"] == 0.9
        # Normalized against the real image_width/height the server reported,
        # not a guessed/stale Video.width -- (10/100, 20/200, (30-10)/100, (180-20)/200)
        assert box["bbox"] == {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.8}
        assert frames[1].detections == []

        assert len(frames[0].ball_detections) == 1
        ball = frames[0].ball_detections[0]
        assert ball["confidence"] == 0.25
        # (40/100, 60/200, (50-40)/100, (70-60)/200)
        assert ball["bbox"] == {"x": 0.4, "y": 0.3, "width": 0.1, "height": 0.05}
        # A single, non-recurring ball detection is never a static false
        # positive -- there's nothing for it to have recurred against.
        assert ball["is_static_false_positive"] is False
        assert frames[1].ball_detections == []


def test_flags_a_ball_position_that_recurs_across_many_seconds(
    sqlite_session_factory, monkeypatch, tmp_path
):
    """Direct regression test for the real false positive found against
    Nh2l4GY8JYI.mp4: a "ball" detected at essentially the same screen
    position for 12+ consecutive seconds, which is impossible for a real
    ball in active play. 11 frames at an explicit 1.0fps (independent of
    whatever the worker's own env default happens to be) span 10 real
    seconds -- wide enough that every frame has some other same-spot
    detection at least 5s away (the flagging threshold), not just the
    two endpoints of the span."""
    from volley_worker.detection import run_video_detection

    _seed_video_with_pipeline_run(sqlite_session_factory)
    frame_count = 11
    frame_paths = _make_frame_files(tmp_path, frame_count)
    # A static "ball" at the same spot in every frame, plus one genuinely
    # different, non-recurring ball detection mixed in for contrast.
    frame_payloads = [
        {
            "image_width": 100,
            "image_height": 100,
            "boxes": [],
            "balls": [{"x1": 39, "y1": 55, "x2": 41, "y2": 57, "confidence": 0.2}],
        }
        for _ in range(frame_count)
    ]
    frame_payloads[5]["balls"].append({"x1": 5, "y1": 5, "x2": 7, "y2": 7, "confidence": 0.9})
    _patch_common(monkeypatch, frame_paths=frame_paths, frame_payloads=frame_payloads)

    result = run_video_detection.run(pipeline_run_id="pr1", video_id="v1", sample_fps=1.0)
    assert result["status"] == "completed"

    with sqlite_session_factory() as db:
        model_run = db.query(ModelRun).filter_by(pipeline_run_id="pr1").one()
        frames = db.query(VideoDetectionFrame).filter_by(model_run_id=model_run.id).all()
        for frame in frames:
            static_ball = next(b for b in frame.ball_detections if b["confidence"] == 0.2)
            assert static_ball["is_static_false_positive"] is True

        moving_frame = next(f for f in frames if f.frame_index == 6)
        moving_ball = next(b for b in moving_frame.ball_detections if b["confidence"] == 0.9)
        assert moving_ball["is_static_false_positive"] is False


def test_max_duration_seconds_is_passed_through_to_frame_extraction(
    sqlite_session_factory, monkeypatch, tmp_path
):
    from volley_worker.detection import run_video_detection

    _seed_video_with_pipeline_run(sqlite_session_factory)
    extract_calls: list[float | None] = []
    _patch_common(
        monkeypatch,
        frame_paths=_make_frame_files(tmp_path, 1),
        frame_payloads=[{"image_width": 100, "image_height": 100, "boxes": [], "balls": []}],
        extract_calls=extract_calls,
    )

    run_video_detection.run(pipeline_run_id="pr1", video_id="v1", max_duration_seconds=1200.0)

    assert extract_calls == [1200.0]
    with sqlite_session_factory() as db:
        model_run = db.query(ModelRun).filter_by(pipeline_run_id="pr1").one()
        assert model_run.metrics["max_duration_seconds"] == 1200.0


def test_start_offset_seconds_is_passed_through_and_offsets_stored_timestamps(
    sqlite_session_factory, monkeypatch, tmp_path
):
    """A caller skipping a match's warmup footage (e.g. "start at 6:52")
    must get frames whose stored timestamp_seconds reflects position in the
    *original* untrimmed video, not position in the trimmed extracted clip
    -- otherwise the frontend's overlay-to-<video>.currentTime sync would be
    silently wrong for any start_offset_seconds > 0."""
    from volley_worker.detection import run_video_detection

    _seed_video_with_pipeline_run(sqlite_session_factory)
    frame_paths = _make_frame_files(tmp_path, 2)
    extract_kwargs: list[dict] = []

    import volley_worker.detection as detection_module

    monkeypatch.setattr(detection_module, "get_storage_adapter", lambda: _FakeAdapter())

    def _fake_extract(source, out_dir, fps, max_duration_seconds=None, start_offset_seconds=None):
        extract_kwargs.append(
            {
                "max_duration_seconds": max_duration_seconds,
                "start_offset_seconds": start_offset_seconds,
            }
        )
        return frame_paths

    monkeypatch.setattr(detection_module, "extract_frames_at_fps", _fake_extract)
    client = _FakeClient(
        health_payload={
            "status": "ok",
            "model_version": "rfdetr-nano-test",
            "weights_sha256": "f" * 64,
        },
        frame_payloads=[
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
        ],
    )
    monkeypatch.setattr(detection_module.httpx, "Client", lambda **_: client)

    result = run_video_detection.run(
        pipeline_run_id="pr1", video_id="v1", start_offset_seconds=412.0, sample_fps=1.0
    )
    assert result["status"] == "completed"
    assert extract_kwargs == [{"max_duration_seconds": None, "start_offset_seconds": 412.0}]

    with sqlite_session_factory() as db:
        model_run = db.query(ModelRun).filter_by(pipeline_run_id="pr1").one()
        assert model_run.metrics["start_offset_seconds"] == 412.0
        frames = (
            db.query(VideoDetectionFrame)
            .filter_by(model_run_id=model_run.id)
            .order_by(VideoDetectionFrame.frame_index)
            .all()
        )
        # sample_fps=1.0 explicitly passed above -- frame 1 lands at
        # offset+0s, frame 2 at offset+1s, not at 0s/1s from the clip start.
        assert [frame.timestamp_seconds for frame in frames] == [412.0, 413.0]


def test_sample_fps_override_is_passed_through_and_used_for_timestamps(
    sqlite_session_factory, monkeypatch, tmp_path
):
    """A caller-supplied sample_fps (e.g. a coach paying for denser ball
    coverage on one short window) must override the worker's env-configured
    default -- both for the real ffmpeg extraction rate and for the stored
    per-frame timestamps, which are derived from whatever rate was actually
    used, not the env default."""
    from volley_worker.detection import run_video_detection

    _seed_video_with_pipeline_run(sqlite_session_factory)
    frame_paths = _make_frame_files(tmp_path, 3)
    fps_calls: list[float] = []
    _patch_common(
        monkeypatch,
        frame_paths=frame_paths,
        frame_payloads=[
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
        ],
        fps_calls=fps_calls,
    )

    result = run_video_detection.run(pipeline_run_id="pr1", video_id="v1", sample_fps=5.0)
    assert result["status"] == "completed"
    assert fps_calls == [5.0]

    with sqlite_session_factory() as db:
        model_run = db.query(ModelRun).filter_by(pipeline_run_id="pr1").one()
        assert model_run.metrics["sample_fps"] == 5.0
        frames = (
            db.query(VideoDetectionFrame)
            .filter_by(model_run_id=model_run.id)
            .order_by(VideoDetectionFrame.frame_index)
            .all()
        )
        # 5fps -> 0.2s between samples, not the env default's 1.0s.
        assert [frame.timestamp_seconds for frame in frames] == pytest.approx([0.0, 0.2, 0.4])


def test_frames_total_is_known_before_any_frame_is_processed(
    sqlite_session_factory, monkeypatch, tmp_path
):
    """The whole point of creating ModelRun before the per-frame loop:
    a client polling detection-status mid-run can already see
    `frames_total` -- this is what a progress bar divides by."""
    from volley_worker.detection import run_video_detection

    _seed_video_with_pipeline_run(sqlite_session_factory)
    _patch_common(
        monkeypatch,
        frame_paths=_make_frame_files(tmp_path, 3),
        frame_payloads=[
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
        ],
    )

    run_video_detection.run(pipeline_run_id="pr1", video_id="v1")

    with sqlite_session_factory() as db:
        model_run = db.query(ModelRun).filter_by(pipeline_run_id="pr1").one()
        # frames_total was set at creation time, before any frame ran --
        # still present and correct after completion.
        assert model_run.metrics["frames_total"] == 3


def test_partial_progress_survives_a_mid_run_failure(sqlite_session_factory, monkeypatch, tmp_path):
    """Directly exercises the fix for the real incident in TECH_DEBT.md
    ("a real incident, not a hypothetical") -- an interruption partway
    through must leave the frames already processed persisted, not
    discarded, because each VideoDetectionFrame commits in its own
    transaction rather than being batched until the very end."""
    from volley_worker.detection import run_video_detection

    _seed_video_with_pipeline_run(sqlite_session_factory)
    _patch_common(
        monkeypatch,
        frame_paths=_make_frame_files(tmp_path, 3),
        frame_payloads=[
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
        ],
        fail_after=2,  # the 3rd frame's POST raises, simulating a crash
    )

    with pytest.raises(RuntimeError):
        run_video_detection.run(pipeline_run_id="pr1", video_id="v1")

    with sqlite_session_factory() as db:
        pipeline_run = db.get(PipelineRun, "pr1")
        assert pipeline_run.status == PipelineRunStatus.FAILED

        model_run = db.query(ModelRun).filter_by(pipeline_run_id="pr1").one()
        assert model_run.metrics["frames_total"] == 3
        # Never reached the final metrics update -- also honest, not a bug.
        assert "frames_processed" not in model_run.metrics

        frames = db.query(VideoDetectionFrame).filter_by(model_run_id=model_run.id).all()
        assert len(frames) == 2


def test_retrying_a_pipeline_run_clears_the_stale_model_run_first(
    sqlite_session_factory, monkeypatch, tmp_path
):
    """A retry restarts frame extraction from the beginning (no
    resume-by-frame-index yet -- see this module's docstring), so the
    orphaned ModelRun/VideoDetectionFrame rows from the abandoned attempt
    must be cleared, not left as a duplicate ModelRun the API's
    single-row lookup can't handle."""
    from volley_worker.detection import run_video_detection

    _seed_video_with_pipeline_run(sqlite_session_factory)
    _patch_common(
        monkeypatch,
        frame_paths=_make_frame_files(tmp_path, 2),
        frame_payloads=[
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
        ],
        fail_after=1,
    )
    with pytest.raises(RuntimeError):
        run_video_detection.run(pipeline_run_id="pr1", video_id="v1")

    with sqlite_session_factory() as db:
        assert db.query(ModelRun).filter_by(pipeline_run_id="pr1").count() == 1
        first_model_run_id = db.query(ModelRun).filter_by(pipeline_run_id="pr1").one().id
        assert db.query(VideoDetectionFrame).filter_by(model_run_id=first_model_run_id).count() == 1
        # A real retry would find pipeline_run.status == FAILED, not
        # RUNNING -- reset it the way the API's dedup logic never would
        # for a FAILED run (it creates a fresh PipelineRun instead), but
        # this task itself doesn't re-check that status, only
        # already-COMPLETED -- so simulate Celery redelivering the same
        # task message directly.

    _patch_common(
        monkeypatch,
        frame_paths=_make_frame_files(tmp_path, 2),
        frame_payloads=[
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
            {"image_width": 100, "image_height": 100, "boxes": [], "balls": []},
        ],
    )
    result = run_video_detection.run(pipeline_run_id="pr1", video_id="v1")
    assert result["status"] == "completed"

    with sqlite_session_factory() as db:
        model_runs = db.query(ModelRun).filter_by(pipeline_run_id="pr1").all()
        assert len(model_runs) == 1
        assert model_runs[0].id != first_model_run_id
        frames = db.query(VideoDetectionFrame).filter_by(model_run_id=model_runs[0].id).all()
        assert len(frames) == 2


def test_unreachable_inference_server_fails_honestly_and_retries(
    sqlite_session_factory, monkeypatch, tmp_path
):
    from volley_worker.detection import run_video_detection

    _seed_video_with_pipeline_run(sqlite_session_factory)
    _patch_common(monkeypatch, frame_paths=_make_frame_files(tmp_path, 1), connect_error=True)

    # self.retry() has no active task request/broker connection here (.run()
    # bypasses the real task machinery) -- Celery's own raise_with_context
    # re-raises the *original* exception in that case rather than its Retry
    # control exception, matching test_ingest.py's identical precedent.
    with pytest.raises(httpx.ConnectError):
        run_video_detection.run(pipeline_run_id="pr1", video_id="v1")

    with sqlite_session_factory() as db:
        pipeline_run = db.get(PipelineRun, "pr1")
        assert pipeline_run.status == PipelineRunStatus.FAILED
        assert "inference server unreachable" in pipeline_run.error
        assert "uv run --project ml" in pipeline_run.error


def test_missing_original_asset_fails_without_retry(sqlite_session_factory, monkeypatch):
    from volley_worker.detection import run_video_detection

    with sqlite_session_factory() as db:
        db.add(
            Video(
                id="v1",
                organization_id="org1",
                filename="clip.mp4",
                uploaded_by_user_id="user1",
                status=VideoStatus.READY,
            )
        )
        db.add(
            PipelineRun(
                id="pr1",
                video_id="v1",
                pipeline_version="video-detection-exploratory-v1",
                config_hash="pending",
                status=PipelineRunStatus.QUEUED,
            )
        )
        db.commit()

    _patch_common(monkeypatch, frame_paths=[])
    result = run_video_detection.run(pipeline_run_id="pr1", video_id="v1")
    assert result["status"] == "failed"

    with sqlite_session_factory() as db:
        pipeline_run = db.get(PipelineRun, "pr1")
        assert pipeline_run.status == PipelineRunStatus.FAILED
        assert "original storage reference" in pipeline_run.error
