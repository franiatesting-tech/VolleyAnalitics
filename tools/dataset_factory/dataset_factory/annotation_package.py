"""Build a frozen, auditable CVAT work package from an acquired clip pool."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from volley_domain.annotation import cvat_task_labels_config


def build_annotation_package(
    inventory: dict[str, Any],
    split_manifest: dict[str, Any],
) -> dict[str, Any]:
    clips = inventory.get("clips", [])
    split_by_clip = split_manifest.get("split_by_video_id", {})
    tasks: list[dict[str, Any]] = []
    missing_splits: list[str] = []

    for clip in sorted(clips, key=lambda item: item["clip_id"]):
        clip_id = clip["clip_id"]
        split = split_by_clip.get(clip_id)
        if split is None:
            missing_splits.append(clip_id)
            continue

        active_play = clip.get("sample_role", "active_play") == "active_play"
        tasks.append(
            {
                "task_name": f"{inventory['plan_version']}--{clip_id}",
                "clip_id": clip_id,
                "media_path": f"clips/{clip['file_name']}",
                "media_sha256": clip["sha256"],
                "source_video_id": clip["source_video_id"],
                "source_url": clip.get("source_url"),
                "source_title": clip.get("title"),
                "source_segment_start_seconds": clip.get("segment_start_seconds"),
                "source_segment_end_seconds": clip.get("segment_end_seconds"),
                "split": split,
                "sample_role": clip.get("sample_role", "active_play"),
                "teams": clip.get("teams", []),
                "competition": clip.get("competition"),
                "court_group": clip.get("court_group"),
                "video": {
                    "width": clip["probe"]["width"],
                    "height": clip["probe"]["height"],
                    "fps": clip["probe"]["fps"],
                    "duration_seconds": clip["probe"]["duration_seconds"],
                    "estimated_frame_count": round(
                        clip["probe"]["duration_seconds"] * clip["probe"]["fps"]
                    ),
                },
                "annotation_scope": (
                    {
                        "court_keypoints": "one complete 10-point set per static camera shot",
                        "player_tracks": "interpolated tracks; verify at least every 5 frames",
                        "ball_points": "every source frame during active rallies; mark occlusion",
                        "pose_keypoints": (
                            "23 body/foot points at 10 fps across rallies and every frame "
                            "from 10 frames before to 10 after each contact"
                        ),
                        "ball_contacts": (
                            "exact frame, actor, team, action and contact surface for every touch"
                        ),
                        "rally_boundaries": "start/end spans for every rally",
                        "action_spans": "serve, reception, set, attack, block and dig spans",
                        "biomechanics_phases": (
                            "approach, takeoff, contact/block and landing spans for jump actions"
                        ),
                    }
                    if active_play
                    else {
                        "negative_review": (
                            "confirm transition/empty-court interval and remove false positives"
                        )
                    }
                ),
                "annotation_status": "pending_human_annotation",
                "review_status": "pending_independent_review",
            }
        )

    if missing_splits:
        raise ValueError(
            "annotation package cannot be frozen; clips lack split assignment: "
            + ", ".join(sorted(missing_splits))
        )

    return {
        "dataset_version": inventory["plan_version"],
        "rights_source_id": inventory.get("rights_source_id"),
        "generated_at": datetime.now(UTC).isoformat(),
        "source_inventory_generated_at": inventory.get("generated_at"),
        "labels": cvat_task_labels_config(
            include_court=True,
            include_rallies=True,
            include_pose=True,
            include_contacts=True,
            include_biomechanics=True,
        ),
        "review_policy": {
            "all_tasks_require_review": True,
            "minimum_double_review_fraction": 0.2,
            "ball_labels_require_frame_level_review": True,
            "all_contact_frames_require_double_review": True,
            "court_calibrations_require_double_review": True,
            "pose_at_contact_requires_double_review": True,
            "split_is_locked_before_annotation": True,
        },
        "tasks": tasks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    split_manifest = json.loads(args.split.read_text(encoding="utf-8"))
    package = build_annotation_package(inventory, split_manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Prepared {len(package['tasks'])} CVAT tasks in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
