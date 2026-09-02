"""Tests for the ingest_video Celery task (services/worker/src/volley_worker/ingest.py).

Two groups:
- Fully mocked logic tests (always run, any environment): exercise the
  task's own control flow -- missing row, already-ready no-op, duplicate
  detection, failure -> retry -- without depending on a real ffmpeg binary
  or a real StorageAdapter backend.
- A real end-to-end test (skipped if no ffmpeg on PATH) using a genuine
  LocalFilesystemStorageAdapter and a real ffmpeg-generated synthetic clip
  (see test_ffprobe.py's synthetic_clip fixture pattern) -- proves the
  actual pipeline plumbing works, not just that the mocks were called
  correctly. Only the D-006 license-build check is stubbed out here (it has
  its own dedicated, rigorous test in test_ffprobe.py); everything else --
  storage I/O, hashing, ffprobe -- is real.
"""

import shutil
import subprocess
from dataclasses import dataclass

import pytest
from volley_domain.ontology import Video, VideoStatus

_FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _seed_video(session_factory, video_id="v1", organization_id="org1", video_hash=None):
    with session_factory() as db:
        db.add(
            Video(
                id=video_id,
                organization_id=organization_id,
                filename="clip.mp4",
                uploaded_by_user_id="user1",
                status=VideoStatus.UPLOADED,
                video_hash=video_hash,
            )
        )
        db.commit()


# ---------------------------------------------------------------------------
# Fully mocked logic tests
# ---------------------------------------------------------------------------


@dataclass
class _FakeProbeResult:
    codec: str = "mpeg4"
    container_format: str = "mov,mp4,m4a,3gp,3g2,mj2"
    duration_seconds: float = 2.0
    fps: float = 25.0
    width: int = 640
    height: int = 360
    start_time_seconds: float = 0.0
    time_base: str = "1/90000"


class _FakeAdapter:
    def download_to_path(self, key, destination):
        return destination


def _patch_common(
    monkeypatch,
    *,
    probe_result=None,
    sha256_value="a" * 64,
    raise_on_probe=None,
    ffprobe_fingerprint=("ffprobe version 7.1 Copyright...", "configuration: --enable-shared"),
):
    import volley_worker.ingest as ingest_module

    monkeypatch.setattr(ingest_module, "verify_ffmpeg_build_is_license_clean", lambda: None)
    monkeypatch.setattr(ingest_module, "get_storage_adapter", lambda: _FakeAdapter())
    monkeypatch.setattr(ingest_module, "compute_sha256", lambda path: sha256_value)
    monkeypatch.setattr(ingest_module, "get_ffprobe_build_fingerprint", lambda: ffprobe_fingerprint)

    def _fake_probe(path):
        if raise_on_probe is not None:
            raise raise_on_probe
        return probe_result or _FakeProbeResult()

    monkeypatch.setattr(ingest_module, "probe_video", _fake_probe)


def test_raises_if_video_row_missing(sqlite_session_factory, monkeypatch):
    from volley_worker.ingest import ingest_video

    _patch_common(monkeypatch)
    with pytest.raises(ValueError):
        ingest_video.run(video_id="does-not-exist", storage_key="org1/videos/x/original/clip.mp4")


def test_already_ready_is_a_noop(sqlite_session_factory, monkeypatch):
    from volley_worker.ingest import ingest_video

    _seed_video(sqlite_session_factory)
    with sqlite_session_factory() as db:
        video = db.get(Video, "v1")
        video.status = VideoStatus.READY
        video.video_hash = "already-hashed"
        db.commit()

    _patch_common(monkeypatch)
    result = ingest_video.run(video_id="v1", storage_key="org1/videos/v1/original/clip.mp4")
    assert result["status"] == "already_ready"

    with sqlite_session_factory() as db:
        assert db.get(Video, "v1").video_hash == "already-hashed"


def test_success_persists_hash_and_probe_fields(sqlite_session_factory, monkeypatch):
    from volley_worker.ingest import ingest_video

    _seed_video(sqlite_session_factory)
    _patch_common(monkeypatch, sha256_value="deadbeef" * 8)

    result = ingest_video.run(video_id="v1", storage_key="org1/videos/v1/original/clip.mp4")
    assert result["status"] == "ready"

    with sqlite_session_factory() as db:
        video = db.get(Video, "v1")
        assert video.status == VideoStatus.READY
        assert video.video_hash == "deadbeef" * 8
        assert video.codec == "mpeg4"
        assert video.duration_seconds == 2.0
        assert video.fps == 25.0
        assert video.width == 640
        assert video.height == 360
        assert video.start_time_seconds == 0.0
        assert video.time_base == "1/90000"
        assert video.error is None


def test_success_creates_a_pipeline_run_and_ingest_model_run_for_provenance(
    sqlite_session_factory, monkeypatch
):
    """TECH_DEBT.md's now-fixed 'Ingest creates no PipelineRun/ModelRun
    row' entry: probe metadata must carry real provenance (which ffmpeg
    build produced it), not just land on Video with nothing explaining
    where it came from."""
    from volley_domain.ontology import ModelRun, ModelRunStage, PipelineRun, PipelineRunStatus
    from volley_worker.ingest import ingest_video

    _seed_video(sqlite_session_factory)
    _patch_common(
        monkeypatch,
        ffprobe_fingerprint=(
            "ffprobe version 8.1.2-lgpl Copyright (c) 2000-2026",
            "configuration: --enable-shared --enable-version3",
        ),
    )

    ingest_video.run(video_id="v1", storage_key="org1/videos/v1/original/clip.mp4")

    with sqlite_session_factory() as db:
        runs = db.query(PipelineRun).filter(PipelineRun.video_id == "v1").all()
        assert len(runs) == 1
        pipeline_run = runs[0]
        assert pipeline_run.status == PipelineRunStatus.COMPLETED
        assert pipeline_run.pipeline_version == "ingest-v1"
        assert pipeline_run.config_hash  # non-empty, deterministic hash of the ffmpeg build config

        model_runs = db.query(ModelRun).filter(ModelRun.pipeline_run_id == pipeline_run.id).all()
        assert len(model_runs) == 1
        model_run = model_runs[0]
        assert model_run.stage == ModelRunStage.INGEST
        assert model_run.model_version == "ffprobe version 8.1.2-lgpl Copyright (c) 2000-2026"
        assert model_run.metrics["codec"] == "mpeg4"
        assert model_run.metrics["fps"] == 25.0


def test_pipeline_run_config_hash_changes_when_the_ffmpeg_build_changes(
    sqlite_session_factory, monkeypatch
):
    """The whole point of hashing the ffmpeg build's own configuration
    string: two different builds probing the same bytes must be
    distinguishable in the provenance chain, not silently collapsed into
    one 'ingest-v1' bucket."""
    from volley_domain.ontology import PipelineRun
    from volley_worker.ingest import ingest_video

    _seed_video(sqlite_session_factory, video_id="v1")
    _patch_common(
        monkeypatch, sha256_value="a" * 64, ffprobe_fingerprint=("v1", "configuration: --build-a")
    )
    ingest_video.run(video_id="v1", storage_key="org1/videos/v1/original/clip.mp4")

    _seed_video(sqlite_session_factory, video_id="v2")
    _patch_common(
        monkeypatch, sha256_value="b" * 64, ffprobe_fingerprint=("v1", "configuration: --build-b")
    )
    ingest_video.run(video_id="v2", storage_key="org1/videos/v2/original/clip.mp4")

    with sqlite_session_factory() as db:
        hash_a = db.query(PipelineRun).filter(PipelineRun.video_id == "v1").one().config_hash
        hash_b = db.query(PipelineRun).filter(PipelineRun.video_id == "v2").one().config_hash
        assert hash_a != hash_b


def test_duplicate_hash_within_org_fails_without_overwriting_the_original(
    sqlite_session_factory, monkeypatch
):
    from volley_worker.ingest import ingest_video

    _seed_video(sqlite_session_factory, video_id="original", video_hash="shared-hash")
    with sqlite_session_factory() as db:
        db.get(Video, "original").status = VideoStatus.READY
        db.commit()

    _seed_video(sqlite_session_factory, video_id="new-upload")
    _patch_common(monkeypatch, sha256_value="shared-hash")

    result = ingest_video.run(
        video_id="new-upload", storage_key="org1/videos/new-upload/original/clip.mp4"
    )
    assert result["status"] == "duplicate"
    assert result["duplicate_of"] == "original"

    with sqlite_session_factory() as db:
        new_video = db.get(Video, "new-upload")
        assert new_video.status == VideoStatus.FAILED
        assert "original" in new_video.error

        original = db.get(Video, "original")
        assert original.status == VideoStatus.READY  # untouched


def test_duplicate_hash_across_orgs_does_not_collide(sqlite_session_factory, monkeypatch):
    """The same content_hash in a *different* organization must never be
    treated as a duplicate -- org isolation applies to content-addressing
    too, not just row visibility (see CLAUDE.md's org-scoping rule)."""
    from volley_worker.ingest import ingest_video

    _seed_video(
        sqlite_session_factory,
        video_id="org1-video",
        organization_id="org1",
        video_hash="same-hash",
    )
    with sqlite_session_factory() as db:
        db.get(Video, "org1-video").status = VideoStatus.READY
        db.commit()

    _seed_video(sqlite_session_factory, video_id="org2-video", organization_id="org2")
    _patch_common(monkeypatch, sha256_value="same-hash")

    result = ingest_video.run(
        video_id="org2-video", storage_key="org2/videos/org2-video/original/clip.mp4"
    )
    assert result["status"] == "ready"


def test_probe_failure_marks_failed_and_retries(sqlite_session_factory, monkeypatch):
    from volley_worker.ffprobe import FfprobeFailedError
    from volley_worker.ingest import ingest_video

    _seed_video(sqlite_session_factory)
    _patch_common(monkeypatch, raise_on_probe=FfprobeFailedError("corrupt container"))

    # self.retry() is called with no active task request/broker connection
    # here (.run() bypasses the real task machinery -- same as this
    # project's other direct .run() task tests, see test_tasks.py) --
    # Celery's own raise_with_context re-raises the *original* exception in
    # that case rather than its Retry control exception, since it has
    # nothing to actually schedule a retry against.
    with pytest.raises(FfprobeFailedError):
        ingest_video.run(video_id="v1", storage_key="org1/videos/v1/original/clip.mp4")

    with sqlite_session_factory() as db:
        video = db.get(Video, "v1")
        assert video.status == VideoStatus.FAILED
        assert "corrupt container" in video.error


def test_refuses_a_storage_key_that_does_not_belong_to_the_video_s_org(
    sqlite_session_factory, monkeypatch
):
    """The task trusts both of its own arguments (video_id, storage_key)
    with no cross-check between them by default -- anyone able to enqueue
    a task on Valkey (not just the API) could otherwise point one org's
    Video row at another org's storage key. Caught by independent security
    review; this is the regression test for the fix."""
    from volley_worker.ingest import ingest_video

    _seed_video(sqlite_session_factory, video_id="v1", organization_id="org1")
    _patch_common(monkeypatch)

    with pytest.raises(ValueError, match="does not belong to video"):
        ingest_video.run(video_id="v1", storage_key="org2/videos/v1/original/clip.mp4")

    with sqlite_session_factory() as db:
        video = db.get(Video, "v1")
        # Never even reached VALIDATING -- the mismatch is caught before
        # the status flip, so a legitimate retry with the correct key
        # isn't blocked by a stuck idempotency-guard status.
        assert video.status == VideoStatus.UPLOADED


def test_license_violation_and_unsafe_media_fail_immediately_without_retrying(
    sqlite_session_factory, monkeypatch
):
    """FfmpegLicenseViolationError and UnsafeMediaFileError are both
    non-transient (a non-compliant ffmpeg build or a text-disguised-as-video
    file will still be exactly that on the next attempt), so retrying them
    three times is semantically wrong and buries the real signal in retry
    noise -- flagged by independent architecture review. This asserts the
    task raises the original exception directly rather than going through
    self.retry()."""
    from volley_worker.ffprobe import FfmpegLicenseViolationError, UnsafeMediaFileError
    from volley_worker.ingest import ingest_video

    for video_id, exc in (
        ("v1", FfmpegLicenseViolationError("GPL build detected")),
        ("v2", UnsafeMediaFileError("looks like text, not video")),
    ):
        _seed_video(sqlite_session_factory, video_id=video_id)
        _patch_common(monkeypatch, raise_on_probe=exc)

        with pytest.raises(type(exc)):
            ingest_video.run(
                video_id=video_id, storage_key=f"org1/videos/{video_id}/original/clip.mp4"
            )

        with sqlite_session_factory() as db:
            video = db.get(Video, video_id)
            assert video.status == VideoStatus.FAILED
            assert str(exc) in video.error


# ---------------------------------------------------------------------------
# Real end-to-end (storage I/O + real ffprobe), skipped if no ffmpeg on PATH
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not found on PATH")
def test_end_to_end_against_a_real_local_storage_adapter_and_real_synthetic_clip(
    sqlite_session_factory, monkeypatch, tmp_path
):
    import volley_worker.ingest as ingest_module
    from volley_storage.local import LocalFilesystemStorageAdapter

    clip_path = tmp_path / "source_clip.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=160x120:rate=15",
            "-c:v",
            "mpeg4",
            "-y",
            str(clip_path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )

    adapter = LocalFilesystemStorageAdapter(
        base_dir=tmp_path / "bucket", base_url="http://localhost:8000", signing_secret="test"
    )
    storage_key = "org1/videos/v1/original/clip.mp4"
    adapter.write_object(storage_key, [clip_path.read_bytes()])

    monkeypatch.setattr(ingest_module, "verify_ffmpeg_build_is_license_clean", lambda: None)
    monkeypatch.setattr(ingest_module, "get_storage_adapter", lambda: adapter)

    _seed_video(sqlite_session_factory)
    from volley_worker.ingest import ingest_video

    result = ingest_video.run(video_id="v1", storage_key=storage_key)
    assert result["status"] == "ready"

    with sqlite_session_factory() as db:
        video = db.get(Video, "v1")
        assert video.status == VideoStatus.READY
        assert video.video_hash is not None and len(video.video_hash) == 64
        assert video.codec == "mpeg4"
        assert video.duration_seconds is not None and 0.5 < video.duration_seconds < 1.5
        assert video.fps is not None and 14.0 < video.fps < 16.0
