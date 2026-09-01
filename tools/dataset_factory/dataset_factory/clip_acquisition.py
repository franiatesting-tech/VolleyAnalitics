"""Acquire short, rights-cleared source clips with reproducible provenance.

The tool deliberately downloads *segments*, not entire source videos. Every
clip is described by a checked-in plan, grouped by its full source video for
leakage-safe splitting, probed after acquisition, content-addressed, and given
a midpoint preview for visual QA. It invokes ``python -m yt_dlp`` and the
``ffmpeg``/``ffprobe`` binaries available in the execution environment; the
supported project path is the pinned worker image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from dataset_factory.source_rights import assert_training_eligible, load_source_manifest


class ClipPlanItem(BaseModel):
    clip_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,79}$")
    source_video_id: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https://(www\.)?youtube\.com/watch\?v=")
    title: str = Field(min_length=1)
    teams: tuple[str, str]
    competition: str = Field(min_length=1)
    court_group: str = Field(min_length=1)
    segment_start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(ge=30, le=180)
    format_selector: str = "298"
    expected_width: int = Field(default=1280, ge=1)
    expected_height: int = Field(default=720, ge=1)
    expected_min_fps: float = Field(default=49.0, gt=0)
    sample_role: Literal["active_play", "transition_negative"] = "active_play"
    tags: list[str] = Field(default_factory=list)

    @field_validator("teams")
    @classmethod
    def _teams_must_be_distinct(cls, value: tuple[str, str]) -> tuple[str, str]:
        if not all(team.strip() for team in value) or value[0] == value[1]:
            raise ValueError("teams must contain two distinct non-empty names")
        return value

    @property
    def segment_end_seconds(self) -> float:
        return self.segment_start_seconds + self.duration_seconds


class ClipPlan(BaseModel):
    version: str = Field(min_length=1)
    created_at: datetime
    purpose: str = Field(min_length=1)
    yt_dlp_version: str = Field(min_length=1)
    ffmpeg_environment: str = Field(min_length=1)
    clips: list[ClipPlanItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _clip_ids_must_be_unique(self) -> ClipPlan:
        ids = [clip.clip_id for clip in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("clip_id values must be unique")
        return self


def load_clip_plan(path: Path) -> ClipPlan:
    return ClipPlan.model_validate_json(path.read_text(encoding="utf-8"))


def _release_tuple(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError as exc:
        raise ValueError(f"Expected a numeric release version, got {version!r}") from exc


def assert_yt_dlp_version(expected: str, installed: str | None = None) -> None:
    installed = installed or metadata.version("yt-dlp")
    if _release_tuple(installed) != _release_tuple(expected):
        raise RuntimeError(f"Clip plan requires yt-dlp {expected}, but {installed} is installed")


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)


def _fraction_to_float(raw: str | None) -> float | None:
    if not raw or raw == "0/0":
        return None
    numerator, separator, denominator = raw.partition("/")
    if separator:
        denominator_value = float(denominator)
        return float(numerator) / denominator_value if denominator_value else None
    return float(raw)


def _probe(path: Path, *, ffprobe_bin: str = "ffprobe") -> dict[str, Any]:
    result = _run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    payload = json.loads(result.stdout)
    stream = next(
        (entry for entry in payload.get("streams", []) if entry.get("codec_type") == "video"),
        None,
    )
    if stream is None:
        raise ValueError(f"No video stream found in {path}")
    format_data = payload.get("format", {})
    return {
        "codec": stream.get("codec_name"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "fps": _fraction_to_float(stream.get("avg_frame_rate")),
        "time_base": stream.get("time_base"),
        "start_time_seconds": float(stream.get("start_time", 0.0)),
        "duration_seconds": float(format_data.get("duration", stream.get("duration", 0.0))),
        "container": format_data.get("format_name"),
    }


def _validate_probe(clip: ClipPlanItem, probe: dict[str, Any]) -> None:
    if probe["width"] != clip.expected_width or probe["height"] != clip.expected_height:
        raise ValueError(
            f"{clip.clip_id}: expected {clip.expected_width}x{clip.expected_height}, "
            f"got {probe['width']}x{probe['height']}"
        )
    if probe["fps"] is None or probe["fps"] < clip.expected_min_fps:
        raise ValueError(
            f"{clip.clip_id}: expected at least {clip.expected_min_fps} fps, got {probe['fps']}"
        )
    if probe["duration_seconds"] < clip.duration_seconds * 0.8:
        raise ValueError(
            f"{clip.clip_id}: acquired duration {probe['duration_seconds']:.2f}s is too short"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _download_full_video_natively(
    source_url: str,
    destination: Path,
    *,
    format_selector: str,
    python_executable: str = sys.executable,
) -> None:
    """Fallback download path for `download_strategy="native_then_local_cut"`
    -- see that parameter's docstring on `acquire_clip` for why this exists.
    Uses yt-dlp's own native downloader (no `--download-sections`, so
    ffmpeg is never involved in the network transfer at all)."""
    _run(
        [
            python_executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--no-part",
            "-f",
            format_selector,
            "-o",
            str(destination),
            source_url,
        ]
    )


def _cut_segment_locally(
    source_path: Path,
    destination: Path,
    *,
    start_seconds: float,
    duration_seconds: float,
    ffmpeg_bin: str = "ffmpeg",
) -> None:
    """ffmpeg operating purely on a local file input -- unlike reading
    directly from a network stream (`--download-sections`'s mechanism),
    this has no network dependency and can't hit the same failure mode."""
    _run(
        [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(start_seconds),
            "-i",
            str(source_path),
            "-t",
            str(duration_seconds),
            "-c",
            "copy",
            str(destination),
        ]
    )


def acquire_clip(
    clip: ClipPlanItem,
    *,
    output_dir: Path,
    python_executable: str = sys.executable,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
    resume: bool = True,
    download_strategy: Literal["ffmpeg_sections", "native_then_local_cut"] = "ffmpeg_sections",
    full_video_cache_dir: Path | None = None,
) -> dict[str, Any]:
    """`download_strategy="native_then_local_cut"` is a fallback for
    environments where ffmpeg's own HTTPS input handling hangs reading
    directly from YouTube's video CDN while yt-dlp's native downloader
    (used for the metadata-only and native-downloader paths) works fine --
    reproduced directly on this project's own dev machine, 2026-08-30 (see
    TECH_DEBT.md): `--download-sections` transferred zero bytes and hung
    indefinitely on three separate attempts (a 6-clip batch, a single 60s
    clip given 8 minutes, a 10-second test clip), while `yt-dlp -f
    <selector>` with no `--download-sections` (i.e. no ffmpeg-as-
    downloader) sustained ~2 MiB/s immediately. This strategy downloads
    the full source video with yt-dlp's native downloader, then cuts the
    target segment with a *local-file* ffmpeg invocation (no network
    dependency, so it can't hit the same hang), trading bandwidth/disk
    (a full source video, not just the needed segment) for reliability on
    an affected network. `full_video_cache_dir` defaults to a sibling of
    `output_dir` and is keyed by `source_video_id` so multiple clips from
    the same source video only trigger one full download."""
    output_dir.mkdir(parents=True, exist_ok=True)
    clip_path = output_dir / f"{clip.clip_id}.mp4"
    info_path = output_dir / f"{clip.clip_id}.info.json"
    preview_path = output_dir / f"{clip.clip_id}.preview.jpg"
    contact_sheet_path = output_dir / f"{clip.clip_id}.contact.jpg"

    if not (resume and clip_path.is_file()):
        if download_strategy == "ffmpeg_sections":
            _run(
                [
                    python_executable,
                    "-m",
                    "yt_dlp",
                    "--no-playlist",
                    "--no-part",
                    "--write-info-json",
                    "--newline",
                    "-f",
                    clip.format_selector,
                    "--download-sections",
                    f"*{clip.segment_start_seconds}-{clip.segment_end_seconds}",
                    "-o",
                    str(output_dir / f"{clip.clip_id}.%(ext)s"),
                    clip.source_url,
                ]
            )
        else:
            cache_dir = full_video_cache_dir or (output_dir.parent / "_full_video_cache")
            cache_dir.mkdir(parents=True, exist_ok=True)
            full_video_path = cache_dir / f"{clip.source_video_id}.mp4"
            if not full_video_path.is_file():
                _download_full_video_natively(
                    clip.source_url,
                    full_video_path,
                    format_selector=clip.format_selector,
                    python_executable=python_executable,
                )
            _cut_segment_locally(
                full_video_path,
                clip_path,
                start_seconds=clip.segment_start_seconds,
                duration_seconds=clip.duration_seconds,
                ffmpeg_bin=ffmpeg_bin,
            )

    if not clip_path.is_file():
        raise FileNotFoundError(f"yt-dlp did not produce expected clip: {clip_path}")

    probe = _probe(clip_path, ffprobe_bin=ffprobe_bin)
    _validate_probe(clip, probe)
    if not preview_path.is_file():
        _run(
            [
                ffmpeg_bin,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(probe["duration_seconds"] / 2),
                "-i",
                str(clip_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(preview_path),
            ]
        )
    if not contact_sheet_path.is_file():
        _run(
            [
                ffmpeg_bin,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(clip_path),
                "-vf",
                "fps=1/12,scale=320:-2,tile=5x1",
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(contact_sheet_path),
            ]
        )

    return {
        **clip.model_dump(mode="json"),
        "segment_end_seconds": clip.segment_end_seconds,
        "file_name": clip_path.name,
        "info_file_name": info_path.name if info_path.is_file() else None,
        "preview_file_name": preview_path.name,
        "contact_sheet_file_name": contact_sheet_path.name,
        "size_bytes": clip_path.stat().st_size,
        "sha256": _sha256(clip_path),
        "probe": probe,
        "acquisition_status": "ready_for_visual_qa",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--rights-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--inventory-out", type=Path, required=True)
    parser.add_argument("--split-units-out", type=Path, required=True)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--download-strategy",
        choices=["ffmpeg_sections", "native_then_local_cut"],
        default="ffmpeg_sections",
        help=(
            "native_then_local_cut is a fallback for environments where ffmpeg's "
            "own HTTPS input hangs reading directly from the video CDN -- see "
            "acquire_clip's docstring and TECH_DEBT.md."
        ),
    )
    args = parser.parse_args(argv)

    rights = load_source_manifest(args.rights_manifest)
    assert_training_eligible([rights])
    plan = load_clip_plan(args.plan)
    assert_yt_dlp_version(plan.yt_dlp_version)

    records: list[dict[str, Any]] = []
    for clip in plan.clips:
        record = acquire_clip(
            clip,
            output_dir=args.output_dir,
            resume=not args.no_resume,
            download_strategy=args.download_strategy,
        )
        records.append(record)
        _write_json(
            args.inventory_out,
            {
                "plan_version": plan.version,
                "generated_at": datetime.now(UTC).isoformat(),
                "rights_source_id": rights.source_id,
                "clips": records,
            },
        )

    _write_json(
        args.split_units_out,
        [
            {
                "video_id": record["clip_id"],
                "group_key": record["source_video_id"],
                "weight": record["probe"]["duration_seconds"],
            }
            for record in records
        ],
    )
    print(f"Acquired and validated {len(records)} clips in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
