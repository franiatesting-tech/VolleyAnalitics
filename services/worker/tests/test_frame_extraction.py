"""Exercises the real ffmpeg frame-extraction subprocess against a
synthetic test clip -- same `synthetic_clip` fixture pattern as
test_ffprobe.py (ffmpeg's own lavfi/testsrc, no real footage). Skipped
entirely when no ffmpeg is on PATH, matching that file's precedent.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
from volley_worker.frame_extraction import (
    FrameExtractionFailedError,
    extract_frames_at_fps,
)

_FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

pytestmark = pytest.mark.skipif(
    not _FFMPEG_AVAILABLE, reason="ffmpeg not found on PATH in this environment"
)


@pytest.fixture(scope="module")
def synthetic_clip(tmp_path_factory) -> Path:
    out_dir = tmp_path_factory.mktemp("synthetic_clip")
    out_path = out_dir / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=4:size=320x240:rate=25",
            "-c:v",
            "mpeg4",
            "-y",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return out_path


@pytest.fixture(scope="module")
def longer_synthetic_clip(tmp_path_factory) -> Path:
    """A 10-second clip, purely for tests that need a meaningful
    start-offset within the clip -- `synthetic_clip` above is intentionally
    just 4s and reused by other tests that assert its exact frame counts."""
    out_dir = tmp_path_factory.mktemp("longer_synthetic_clip")
    out_path = out_dir / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=10:size=320x240:rate=25",
            "-c:v",
            "mpeg4",
            "-y",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return out_path


def test_extracts_the_expected_frame_count_at_a_low_sample_rate(synthetic_clip, tmp_path):
    # A 4-second clip sampled at 0.5fps -> 2 output frames.
    frames = extract_frames_at_fps(synthetic_clip, tmp_path / "out", fps=0.5)
    assert len(frames) == 2
    assert all(frame.is_file() and frame.stat().st_size > 0 for frame in frames)


def test_max_duration_seconds_caps_extraction_to_a_prefix(synthetic_clip, tmp_path):
    # The full 4-second clip at 1fps would give 4 frames -- capping to the
    # first 2 seconds must give 2, not silently ignore the cap.
    frames = extract_frames_at_fps(
        synthetic_clip, tmp_path / "out", fps=1.0, max_duration_seconds=2.0
    )
    assert len(frames) == 2


def test_rejects_a_non_positive_max_duration(synthetic_clip, tmp_path):
    with pytest.raises(ValueError):
        extract_frames_at_fps(synthetic_clip, tmp_path / "out", fps=1.0, max_duration_seconds=0)


def test_start_offset_seconds_skips_the_clip_prefix(longer_synthetic_clip, tmp_path):
    # The full 10-second clip at 1fps would give 10 frames -- starting 6
    # seconds in must give 4 (seconds 6, 7, 8, 9), not silently ignore the
    # offset and still return all 10.
    frames = extract_frames_at_fps(
        longer_synthetic_clip, tmp_path / "out", fps=1.0, start_offset_seconds=6.0
    )
    assert len(frames) == 4


def test_start_offset_and_max_duration_combine_correctly(longer_synthetic_clip, tmp_path):
    # -t measures duration from wherever -ss already seeked to, not from
    # the original start -- must give exactly 3 frames (seconds 6, 7, 8),
    # not 3 frames from the very beginning of the clip.
    frames = extract_frames_at_fps(
        longer_synthetic_clip,
        tmp_path / "out",
        fps=1.0,
        start_offset_seconds=6.0,
        max_duration_seconds=3.0,
    )
    assert len(frames) == 3


def test_rejects_a_negative_start_offset(synthetic_clip, tmp_path):
    with pytest.raises(ValueError):
        extract_frames_at_fps(synthetic_clip, tmp_path / "out", fps=1.0, start_offset_seconds=-1.0)


def test_zero_start_offset_behaves_like_no_offset(synthetic_clip, tmp_path):
    frames = extract_frames_at_fps(
        synthetic_clip, tmp_path / "out", fps=0.5, start_offset_seconds=0.0
    )
    assert len(frames) == 2


def test_frames_are_returned_in_order(synthetic_clip, tmp_path):
    frames = extract_frames_at_fps(synthetic_clip, tmp_path / "out", fps=2.0)
    assert [frame.name for frame in frames] == sorted(frame.name for frame in frames)


def test_rejects_a_non_positive_fps(synthetic_clip, tmp_path):
    with pytest.raises(ValueError):
        extract_frames_at_fps(synthetic_clip, tmp_path / "out", fps=0)


def test_fails_clearly_on_a_nonexistent_source(tmp_path):
    # reject_if_reference_style_media opens the file to sniff its first
    # bytes before ffmpeg ever runs -- a missing source surfaces as
    # FileNotFoundError there, not as FrameExtractionFailedError.
    with pytest.raises(FileNotFoundError):
        extract_frames_at_fps(tmp_path / "does-not-exist.mp4", tmp_path / "out", fps=1.0)


def test_fails_clearly_on_a_corrupt_binary_file(tmp_path):
    # Binary garbage (not printable-ASCII text, so it passes
    # reject_if_reference_style_media's sniff) that ffmpeg still can't
    # decode as any known container -- must surface as
    # FrameExtractionFailedError with ffmpeg's own stderr, not an opaque
    # subprocess exit code.
    garbage = tmp_path / "corrupt.mp4"
    garbage.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(FrameExtractionFailedError):
        extract_frames_at_fps(garbage, tmp_path / "out", fps=1.0)


def test_rejects_a_reference_style_file(tmp_path):
    from volley_worker.ffprobe import UnsafeMediaFileError

    playlist = tmp_path / "fake.m3u8"
    playlist.write_text("#EXTM3U\n#EXT-X-VERSION:3\n")
    with pytest.raises(UnsafeMediaFileError):
        extract_frames_at_fps(playlist, tmp_path / "out", fps=1.0)
