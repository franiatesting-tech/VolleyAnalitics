from datetime import UTC, datetime
from pathlib import Path

import pytest
from dataset_factory.clip_acquisition import (
    ClipPlan,
    ClipPlanItem,
    _fraction_to_float,
    _validate_probe,
    acquire_clip,
    assert_yt_dlp_version,
)
from pydantic import ValidationError


def _clip(**overrides) -> ClipPlanItem:
    values = {
        "clip_id": "match-a-clip-01",
        "source_video_id": "video-a",
        "source_url": "https://www.youtube.com/watch?v=video-a",
        "title": "Team A vs Team B",
        "teams": ("Team A", "Team B"),
        "competition": "Test Cup",
        "court_group": "court-a",
        "segment_start_seconds": 120,
        "duration_seconds": 60,
    }
    values.update(overrides)
    return ClipPlanItem(**values)


def test_clip_plan_rejects_duplicate_ids():
    with pytest.raises(ValidationError, match="clip_id values must be unique"):
        ClipPlan(
            version="v0",
            created_at=datetime.now(UTC),
            purpose="test",
            yt_dlp_version="2026.08.19",
            ffmpeg_environment="test",
            clips=[_clip(), _clip(source_video_id="video-b")],
        )


def test_fraction_to_float_handles_ffprobe_rates():
    assert _fraction_to_float("50/1") == 50.0
    assert _fraction_to_float("30000/1001") == pytest.approx(29.970, rel=1e-3)
    assert _fraction_to_float("0/0") is None


def test_probe_validation_rejects_fake_50fps():
    with pytest.raises(ValueError, match="at least 49.0 fps"):
        _validate_probe(
            _clip(),
            {
                "width": 1280,
                "height": 720,
                "fps": 30.0,
                "duration_seconds": 60.0,
            },
        )


def test_yt_dlp_version_is_pinned_by_the_clip_plan():
    assert_yt_dlp_version("2026.08.19", installed="2026.8.19")
    with pytest.raises(RuntimeError, match="requires yt-dlp 2026.08.19"):
        assert_yt_dlp_version("2026.08.19", installed="2026.9.1")


def test_native_then_local_cut_downloads_full_video_once_and_cuts_locally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Regression for the real environment issue this strategy exists to
    work around (TECH_DEBT.md, 2026-08-30): ffmpeg's own HTTPS input
    handling hung reading directly from the video CDN on this project's
    dev machine, while yt-dlp's native downloader worked. Two clips from
    the *same* source video must trigger exactly one full download and
    two local cuts -- not two full downloads."""
    import dataset_factory.clip_acquisition as module

    commands: list[list[str]] = []

    def _fake_run(command: list[str]):
        commands.append(command)
        if "yt_dlp" in command:
            # Simulate yt-dlp's native downloader producing the full file.
            Path(command[command.index("-o") + 1]).write_bytes(b"full-video-bytes")
        elif command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"cut-clip-bytes")
        return None

    monkeypatch.setattr(module, "_run", _fake_run)
    monkeypatch.setattr(
        module,
        "_probe",
        lambda path, ffprobe_bin="ffprobe": {
            "width": 1280,
            "height": 720,
            "fps": 50.0,
            "duration_seconds": 60.0,
        },
    )
    monkeypatch.setattr(module, "_sha256", lambda path: "deadbeef")

    output_dir = tmp_path / "clips"
    clip_a = _clip(clip_id="match-a", source_video_id="video-shared", segment_start_seconds=100)
    clip_b = _clip(clip_id="match-b", source_video_id="video-shared", segment_start_seconds=500)

    acquire_clip(clip_a, output_dir=output_dir, download_strategy="native_then_local_cut")
    acquire_clip(clip_b, output_dir=output_dir, download_strategy="native_then_local_cut")

    yt_dlp_calls = [c for c in commands if "yt_dlp" in c]
    local_cut_calls = [c for c in commands if c[0] == "ffmpeg" and "-c" in c]
    assert len(yt_dlp_calls) == 1, "the shared source video must only be downloaded once"
    assert len(local_cut_calls) == 2, "each clip still gets its own local cut"
    assert (output_dir / "match-a.mp4").is_file()
    assert (output_dir / "match-b.mp4").is_file()
    assert (output_dir.parent / "_full_video_cache" / "video-shared.mp4").is_file()
