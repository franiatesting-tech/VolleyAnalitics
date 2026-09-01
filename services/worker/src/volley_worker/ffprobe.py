"""ffprobe/ffmpeg wrapper (subprocess, never a Python binding against
libav*/libsw* -- this project never links FFmpeg's libraries into its own
process, see LICENSE_DECISIONS.md D-006). Two independent responsibilities:

1. `probe_video` -- container/codec/duration/fps extraction for the ingest
   pipeline (DATA_FLOW.md's "worker probes container/codec/PTS" step).
2. `verify_ffmpeg_build_is_license_clean` -- the D-006-required runtime
   check that the ffmpeg binary actually on PATH is the pinned LGPL-only
   build (no --enable-gpl/--enable-nonfree, no libx264/libx265/libfdk-aac),
   not a GPL build that silently slipped in via a base-image change or a
   developer's own system ffmpeg. This is deliberately re-checked at
   runtime, not just pinned once in the Dockerfile and trusted forever --
   see that function's docstring for why a Dockerfile pin alone doesn't
   satisfy D-006's "catches a GPL build sneaking in via a dependency
   upgrade" requirement.
"""

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from json import loads
from pathlib import Path

_DISALLOWED_CONFIG_MARKERS = (
    "--enable-gpl",
    "--enable-nonfree",
    "--enable-libx264",
    "--enable-libx265",
    "--enable-libfdk-aac",
    "enable-libx264",
    "enable-libx265",
    "enable-libfdk-aac",
)


class FfmpegNotFoundError(RuntimeError):
    pass


class FfmpegLicenseViolationError(RuntimeError):
    """Raised when the ffmpeg/ffprobe binary on PATH is built with a
    disallowed GPL/nonfree component -- see LICENSE_DECISIONS.md D-006.
    A worker must never process video with a non-compliant build; this is
    a hard startup/runtime failure, not a warning."""


class FfprobeFailedError(RuntimeError):
    pass


class UnsafeMediaFileError(RuntimeError):
    """Raised when a file refuses to be probed because it looks like a
    text-based "reference" format (HLS/DASH playlist, concat-demuxer
    script, etc.) rather than an actual binary video container -- FFmpeg's
    format auto-detection will happily follow such a file's *own*
    references to other paths (including, for an uploaded file, other
    organizations' storage keys), which independent security review
    demonstrated live: an uploaded `.m3u8` playlist referencing
    `../../../other-org/video.ts` made ffprobe read and report metadata
    for a different organization's video entirely. Legitimate binary video
    containers (MP4/MOV, WebM/MKV, AVI, MPEG-TS, ...) are never valid
    printable-ASCII text in their first bytes -- this check is
    deliberately a broad "does this look like text" heuristic rather than
    a narrow "reject exactly .m3u8" signature match, so it also covers the
    concat demuxer's own reference-list format and similar variants we
    didn't specifically test for."""


_TEXT_SNIFF_BYTES = 256
# A handful of control bytes that are common and harmless at the very start
# of legitimate binary containers (e.g. BOM-adjacent bytes) but not
# considered part of "this is human-typed text".
_ALLOWED_NON_PRINTABLE = frozenset({0x09, 0x0A, 0x0D})


def _looks_like_text(data: bytes) -> bool:
    if not data:
        return False
    sample = data[:_TEXT_SNIFF_BYTES]
    return all(32 <= b <= 126 or b in _ALLOWED_NON_PRINTABLE for b in sample)


def reject_if_reference_style_media(path: Path) -> None:
    """Refuses to hand `path` to ffprobe/ffmpeg at all if it looks like a
    text-based reference format rather than a real binary video container.
    Must be called on every untrusted file BEFORE `probe_video` -- see
    `UnsafeMediaFileError`'s docstring for why."""
    with path.open("rb") as f:
        head = f.read(_TEXT_SNIFF_BYTES)
    if _looks_like_text(head):
        raise UnsafeMediaFileError(
            "Refusing to probe a file that looks like text (a playlist/reference "
            "format) rather than a binary video container -- see UnsafeMediaFileError."
        )


@dataclass(frozen=True)
class VideoProbeResult:
    codec: str | None
    container_format: str | None
    duration_seconds: float | None
    fps: float | None
    width: int | None
    height: int | None
    # PTS mapping (DATA_FLOW.md's "Video identity") -- see Video.start_time_seconds
    # / Video.time_base's docstring in ontology.py for why this exists.
    start_time_seconds: float | None
    time_base: str | None


def _run_version(binary: str) -> str:
    exe = shutil.which(binary)
    if exe is None:
        raise FfmpegNotFoundError(f"{binary!r} not found on PATH")
    result = subprocess.run(  # noqa: S603 -- fixed args, no shell, no user input
        [exe, "-version"], capture_output=True, text=True, timeout=10, check=False
    )
    if result.returncode != 0:
        raise FfmpegNotFoundError(f"{binary} -version exited {result.returncode}")
    return result.stdout


def verify_ffmpeg_build_is_license_clean(binaries: tuple[str, ...] = ("ffmpeg", "ffprobe")) -> None:
    """D-006's operationalized check: fails loudly (raises, doesn't warn-and-
    continue) if any disallowed GPL/nonfree marker appears in either
    binary's own reported `configuration:` string. This is the actual
    verification step D-006 required before closing -- run automatically at
    worker startup (celery_app.py) and independently as a CI/test assertion
    (test_ffprobe.py's test_installed_ffmpeg_build_is_license_clean), so a
    future base-image bump that silently reintroduces a GPL build (exactly
    what happened when this project's own default `apt-get install ffmpeg`
    was checked during Phase 4 research and found to ship
    --enable-gpl/--enable-libx264/--enable-libx265 on current Debian
    trixie) is caught immediately rather than discovered later."""
    for binary in binaries:
        version_output = _run_version(binary)
        config_line = next(
            (line for line in version_output.splitlines() if line.startswith("configuration:")),
            "",
        )
        hits = [marker for marker in _DISALLOWED_CONFIG_MARKERS if marker in config_line]
        if hits:
            raise FfmpegLicenseViolationError(
                f"{binary} build is not license-clean per LICENSE_DECISIONS.md D-006 -- "
                f"found disallowed marker(s) {hits} in its configuration string. "
                f"Full configuration line: {config_line!r}"
            )


def get_ffprobe_build_fingerprint() -> tuple[str, str]:
    """Returns (version_line, configuration_line) for the `ffprobe` binary
    currently on PATH. Used by ingest.py to give `probe_video`'s output a
    real PipelineRun/ModelRun provenance record -- CLAUDE.md's Traceability
    section requires every derived value to carry enough provenance to
    explain "why does the product show me this", and probe_video's
    codec/fps/width/height output is deterministic *given this exact
    ffmpeg build*, not universally deterministic (a different build can
    read the same container differently) -- so the build identity is the
    right thing to fingerprint, not just "ffprobe was run"."""
    version_output = _run_version("ffprobe")
    lines = version_output.splitlines()
    version_line = lines[0] if lines else ""
    config_line = next((line for line in lines if line.startswith("configuration:")), "")
    return version_line, config_line


def compute_sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_frame_rate(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        value = Fraction(raw)
    except (ValueError, ZeroDivisionError):
        return None
    if value.denominator == 0:
        return None
    return float(value)


def probe_video(path: Path) -> VideoProbeResult:
    exe = shutil.which("ffprobe")
    if exe is None:
        raise FfmpegNotFoundError("'ffprobe' not found on PATH")

    # Must run before ffprobe ever sees the file -- see
    # UnsafeMediaFileError's docstring. Not redundant with -protocol_whitelist
    # below: that restricts which *protocols* ffmpeg's demuxers may follow
    # (blocks e.g. a concat/hls reference to an http:// URL), this rejects
    # the file outright before any demuxer gets to run its own reference-
    # following logic against local paths in the first place.
    reject_if_reference_style_media(path)

    result = subprocess.run(  # noqa: S603 -- fixed args + a validated local path, no shell
        [
            exe,
            "-v",
            "error",
            # Belt-and-suspenders alongside reject_if_reference_style_media
            # above: restricts ffmpeg's own I/O to local files only, so even
            # a reference-style demuxer that somehow still gets selected
            # can't be steered into fetching a remote URL.
            "-protocol_whitelist",
            "file",
            # Never pass -enable_drefs: ffmpeg's mov demuxer defaults it to
            # false, which is the only thing stopping a binary MP4 (passes
            # reject_if_reference_style_media's text-sniff, since it's a
            # real binary container) from using a `dref` atom to point at
            # another organization's file -- neither the text-sniff nor
            # -protocol_whitelist above catches that vector. Confirmed by
            # independent security review 2026-08-30 (`ffprobe -h
            # demuxer=mov`). If this ever needs to change, re-verify the
            # dref cross-org-read scenario first.
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise FfprobeFailedError(
            f"ffprobe failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    try:
        payload = loads(result.stdout)
    except ValueError as exc:
        raise FfprobeFailedError(f"ffprobe produced non-JSON output: {exc}") from exc

    fmt = payload.get("format", {})
    streams = payload.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)

    duration_raw = fmt.get("duration")
    duration_seconds = float(duration_raw) if duration_raw is not None else None

    codec = video_stream.get("codec_name") if video_stream else None
    fps = _parse_frame_rate(video_stream.get("avg_frame_rate")) if video_stream else None
    container_format = fmt.get("format_name")
    width = video_stream.get("width") if video_stream else None
    height = video_stream.get("height") if video_stream else None
    start_time_raw = video_stream.get("start_time") if video_stream else None
    start_time_seconds = float(start_time_raw) if start_time_raw is not None else None
    time_base = video_stream.get("time_base") if video_stream else None

    return VideoProbeResult(
        codec=codec,
        container_format=container_format,
        duration_seconds=duration_seconds,
        fps=fps,
        width=width,
        height=height,
        start_time_seconds=start_time_seconds,
        time_base=time_base,
    )
