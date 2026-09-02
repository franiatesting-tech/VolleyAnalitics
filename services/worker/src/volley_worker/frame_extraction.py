"""Fixed-rate frame extraction for the exploratory detection pipeline
(volley_worker.detection). Shells out to `ffmpeg` (never a Python binding
against libav*/libsw*, matching ffprobe.py's own D-006 rationale) with the
same safety guards `probe_video` already uses -- this module only ever runs
against a video this worker itself just downloaded via StorageAdapter (see
ingest.py's precedent), but a malformed/hostile container is still worth
defending against the same way.
"""

import shutil
import subprocess
from pathlib import Path

from volley_worker.ffprobe import FfmpegNotFoundError, reject_if_reference_style_media


class FrameExtractionFailedError(RuntimeError):
    pass


def extract_frames_at_fps(
    source: Path,
    out_dir: Path,
    *,
    fps: float,
    max_duration_seconds: float | None = None,
    start_offset_seconds: float | None = None,
) -> list[Path]:
    """Extracts frames sampled at a fixed `fps` (not the source video's own
    frame rate -- CPU-only local inference is far too slow to run every
    frame of a full match, see VideoDetectionFrame's docstring in
    ontology.py) into `out_dir` as sequentially numbered JPEGs. Returns the
    resulting paths in order; the caller derives each frame's position in
    the *extracted* clip as `(ordinal - 1) / fps`, matching ffmpeg's own
    `fps` filter semantics (the Nth output frame is the one nearest
    `(N-1)/fps` seconds into the clip that was actually extracted) --
    add `start_offset_seconds` back on to get the real position in the
    original source video.

    `start_offset_seconds`, when given, skips the video's own first N
    seconds (ffmpeg's `-ss`, placed as an *input* option before `-i` for a
    fast keyframe-based seek -- accurate to within a fraction of a second,
    which is fine for this exploratory pipeline, not frame-perfect
    editing) -- lets a caller skip a real match's warmup/pre-play footage
    and start analysis from the moment play actually begins.
    `max_duration_seconds`, when given, caps extraction to N seconds
    *from that starting point* (ffmpeg's `-t`, an output-duration limit
    that correctly measures from wherever `-ss` already seeked to, not
    from the original start) -- lets a caller deliberately preview/test
    against a short prefix instead of committing CPU-only local inference
    to the entire remaining runtime up front.
    """
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    if max_duration_seconds is not None and max_duration_seconds <= 0:
        raise ValueError(f"max_duration_seconds must be positive, got {max_duration_seconds}")
    if start_offset_seconds is not None and start_offset_seconds < 0:
        raise ValueError(f"start_offset_seconds must be non-negative, got {start_offset_seconds}")

    reject_if_reference_style_media(source)

    exe = shutil.which("ffmpeg")
    if exe is None:
        raise FfmpegNotFoundError("'ffmpeg' not found on PATH")

    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "frame_%06d.jpg"

    seek_args = (
        ["-ss", str(start_offset_seconds)]
        if start_offset_seconds is not None and start_offset_seconds > 0
        else []
    )
    duration_args = ["-t", str(max_duration_seconds)] if max_duration_seconds is not None else []
    result = subprocess.run(  # noqa: S603 -- fixed args + a validated local path, no shell
        [
            exe,
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            *seek_args,
            "-i",
            str(source),
            "-vf",
            f"fps={fps}",
            "-qscale:v",
            "3",
            *duration_args,
            str(pattern),
        ],
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if result.returncode != 0:
        raise FrameExtractionFailedError(
            f"ffmpeg frame extraction failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    return sorted(out_dir.glob("frame_*.jpg"))
