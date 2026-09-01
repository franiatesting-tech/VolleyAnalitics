"""Quality gate for an acquired, still-unlabelled video clip pool."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ClipPoolPolicy:
    min_clips: int = 8
    min_source_videos: int = 5
    min_teams: int = 6
    min_court_groups: int = 2
    min_total_duration_seconds: float = 480.0
    min_active_play_fraction: float = 0.75
    max_transition_negative_fraction: float = 0.25
    required_width: int = 1280
    required_height: int = 720
    min_fps: float = 49.0


@dataclass
class ClipPoolQAReport:
    clip_count: int
    source_video_count: int
    team_count: int
    court_group_count: int
    total_duration_seconds: float
    active_play_count: int
    transition_negative_count: int
    split_counts: dict[str, int]
    duplicate_hashes: list[str] = field(default_factory=list)
    leaking_source_videos: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.violations and not self.duplicate_hashes and not self.leaking_source_videos

    @property
    def readiness(self) -> str:
        return (
            "ready_for_annotation_and_unlabelled_pretraining"
            if self.is_clean
            else "blocked_by_clip_pool_qa"
        )

    def as_json(self) -> dict[str, Any]:
        return {**asdict(self), "is_clean": self.is_clean, "readiness": self.readiness}


def run_clip_pool_qa(
    inventory: dict[str, Any],
    split_manifest: dict[str, Any],
    *,
    policy: ClipPoolPolicy | None = None,
) -> ClipPoolQAReport:
    policy = policy or ClipPoolPolicy()
    clips = inventory.get("clips", [])
    source_ids = {clip["source_video_id"] for clip in clips}
    teams = {team for clip in clips for team in clip.get("teams", [])}
    court_groups = {clip["court_group"] for clip in clips}
    total_duration = sum(float(clip["probe"]["duration_seconds"]) for clip in clips)
    active_count = sum(clip.get("sample_role", "active_play") == "active_play" for clip in clips)
    negative_count = sum(clip.get("sample_role") == "transition_negative" for clip in clips)

    violations: list[str] = []
    if len(clips) < policy.min_clips:
        violations.append(f"clip count {len(clips)} is below {policy.min_clips}")
    if len(source_ids) < policy.min_source_videos:
        violations.append(
            f"source video count {len(source_ids)} is below {policy.min_source_videos}"
        )
    if len(teams) < policy.min_teams:
        violations.append(f"team count {len(teams)} is below {policy.min_teams}")
    if len(court_groups) < policy.min_court_groups:
        violations.append(
            f"court group count {len(court_groups)} is below {policy.min_court_groups}"
        )
    if total_duration < policy.min_total_duration_seconds:
        violations.append(
            f"duration {total_duration:.2f}s is below {policy.min_total_duration_seconds:.2f}s"
        )

    active_fraction = active_count / len(clips) if clips else 0.0
    negative_fraction = negative_count / len(clips) if clips else 1.0
    if active_fraction < policy.min_active_play_fraction:
        violations.append(
            f"active-play fraction {active_fraction:.3f} is below "
            f"{policy.min_active_play_fraction:.3f}"
        )
    if negative_fraction > policy.max_transition_negative_fraction:
        violations.append(
            f"transition-negative fraction {negative_fraction:.3f} exceeds "
            f"{policy.max_transition_negative_fraction:.3f}"
        )

    for clip in clips:
        probe = clip["probe"]
        if (
            probe.get("width") != policy.required_width
            or probe.get("height") != policy.required_height
        ):
            violations.append(f"{clip['clip_id']} is not 1280x720")
        if probe.get("fps") is None or float(probe["fps"]) < policy.min_fps:
            violations.append(f"{clip['clip_id']} is below {policy.min_fps} fps")
        if clip.get("acquisition_status") != "ready_for_visual_qa":
            violations.append(f"{clip['clip_id']} acquisition is not ready")

    clip_ids_by_hash: dict[str, list[str]] = defaultdict(list)
    for clip in clips:
        clip_ids_by_hash[clip["sha256"]].append(clip["clip_id"])
    duplicate_hashes = sorted(
        digest for digest, clip_ids in clip_ids_by_hash.items() if len(clip_ids) > 1
    )

    split_by_clip = split_manifest.get("split_by_video_id", {})
    split_counts: dict[str, int] = defaultdict(int)
    splits_by_source: dict[str, set[str]] = defaultdict(set)
    for clip in clips:
        split = split_by_clip.get(clip["clip_id"])
        if split is None:
            violations.append(f"{clip['clip_id']} has no split assignment")
            continue
        split_counts[split] += 1
        splits_by_source[clip["source_video_id"]].add(split)
    leaking = sorted(source for source, splits in splits_by_source.items() if len(splits) > 1)
    for required_split in ("train", "val", "test"):
        if not split_counts.get(required_split):
            violations.append(f"split {required_split} is empty")

    return ClipPoolQAReport(
        clip_count=len(clips),
        source_video_count=len(source_ids),
        team_count=len(teams),
        court_group_count=len(court_groups),
        total_duration_seconds=round(total_duration, 3),
        active_play_count=active_count,
        transition_negative_count=negative_count,
        split_counts=dict(split_counts),
        duplicate_hashes=duplicate_hashes,
        leaking_source_videos=leaking,
        violations=violations,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    split_manifest = json.loads(args.split.read_text(encoding="utf-8"))
    report = run_clip_pool_qa(inventory, split_manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report.as_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.as_json(), indent=2, sort_keys=True))
    return 0 if report.is_clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
