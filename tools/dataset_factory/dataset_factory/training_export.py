"""Export reviewed volleyball signals into deterministic training manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel
from volley_domain.annotation import (
    VOLLEY_SKELETON_EDGES,
    VOLLEY_SKELETON_KEYPOINTS,
    BallFrameAnnotation,
    PlayerBBoxAnnotation,
    PlayerPoseFrameAnnotation,
)

ModelT = TypeVar("ModelT", bound=BaseModel)
FrameKey = tuple[str, str, int]
PERSON_ROLES = (
    "on_court_player",
    "substitute",
    "official",
    "staff",
    "spectator",
)


def _frame_key(video_id: str, rally_id: str, frame_index: int) -> FrameKey:
    return video_id, rally_id, frame_index


def _file_name(key: FrameKey) -> str:
    video_id, _, frame_index = key
    return f"frames/{video_id}/{frame_index:08d}.jpg"


def _coco_visibility(state: str) -> int:
    if state == "visible":
        return 2
    if state in {"occluded", "uncertain"}:
        return 1
    return 0


def _build_images(
    keys: list[FrameKey],
    image_size_by_video_id: dict[str, tuple[int, int]],
) -> tuple[list[dict[str, Any]], dict[FrameKey, int]]:
    image_id_by_key = {key: index for index, key in enumerate(keys, start=1)}
    images = []
    for key in keys:
        width, height = image_size_by_video_id[key[0]]
        images.append(
            {
                "id": image_id_by_key[key],
                "file_name": _file_name(key),
                "width": width,
                "height": height,
                "video_id": key[0],
                "rally_id": None if key[1] == "unassigned-rally" else key[1],
                "frame_index": key[2],
            }
        )
    return images, image_id_by_key


def _assert_reviewed(items: list[ModelT], *, signal_name: str) -> None:
    unreviewed = [
        f"{item.provenance.video_id}:{item.frame.frame_index}"  # type: ignore[attr-defined]
        for item in items
        if not item.provenance.reviewed  # type: ignore[attr-defined]
    ]
    if unreviewed:
        sample = ", ".join(unreviewed[:5])
        suffix = " ..." if len(unreviewed) > 5 else ""
        raise ValueError(
            f"{signal_name} contains {len(unreviewed)} unreviewed labels: {sample}{suffix}"
        )


def build_training_exports(
    poses: list[PlayerPoseFrameAnnotation],
    ball_frames: list[BallFrameAnnotation],
    *,
    player_boxes: list[PlayerBBoxAnnotation] | None = None,
    split_by_video_id: dict[str, str],
    image_size_by_video_id: dict[str, tuple[int, int]],
) -> dict[str, dict[str, Any]]:
    player_boxes = player_boxes or []
    _assert_reviewed(player_boxes, signal_name="player boxes")
    _assert_reviewed(poses, signal_name="poses")
    _assert_reviewed(ball_frames, signal_name="ball frames")

    detection_keys = {
        _frame_key(item.provenance.video_id, "unassigned-rally", item.frame.frame_index)
        for item in player_boxes
    }
    pose_keys = {
        _frame_key(item.provenance.video_id, item.rally_id, item.frame.frame_index)
        for item in poses
    }
    ball_keys = {
        _frame_key(item.provenance.video_id, item.rally_id, item.frame.frame_index)
        for item in ball_frames
    }
    frame_keys = detection_keys | pose_keys | ball_keys
    missing_split = sorted({key[0] for key in frame_keys if key[0] not in split_by_video_id})
    missing_size = sorted({key[0] for key in frame_keys if key[0] not in image_size_by_video_id})
    if missing_split:
        raise ValueError(f"videos lack split assignment: {', '.join(missing_split)}")
    if missing_size:
        raise ValueError(f"videos lack image dimensions: {', '.join(missing_size)}")

    exports: dict[str, dict[str, Any]] = {}
    splits = sorted({split_by_video_id[key[0]] for key in frame_keys})
    for split in splits:
        split_detection_keys = sorted(
            key for key in detection_keys if split_by_video_id[key[0]] == split
        )
        split_pose_keys = sorted(key for key in pose_keys if split_by_video_id[key[0]] == split)
        split_ball_keys = sorted(key for key in ball_keys if split_by_video_id[key[0]] == split)
        detection_images, detection_image_id_by_key = _build_images(
            split_detection_keys, image_size_by_video_id
        )
        pose_images, pose_image_id_by_key = _build_images(split_pose_keys, image_size_by_video_id)
        _, ball_image_id_by_key = _build_images(split_ball_keys, image_size_by_video_id)

        detection_annotations = []
        annotation_id = 1
        for box in sorted(
            (item for item in player_boxes if split_by_video_id[item.provenance.video_id] == split),
            key=lambda item: (
                item.provenance.video_id,
                item.frame.frame_index,
                item.track_id,
            ),
        ):
            key = _frame_key(
                box.provenance.video_id,
                "unassigned-rally",
                box.frame.frame_index,
            )
            width, height = image_size_by_video_id[key[0]]
            bbox = [
                box.bbox.x * width,
                box.bbox.y * height,
                box.bbox.width * width,
                box.bbox.height * height,
            ]
            detection_annotations.append(
                {
                    "id": annotation_id,
                    "image_id": detection_image_id_by_key[key],
                    "category_id": PERSON_ROLES.index(box.person_role) + 1,
                    "bbox": bbox,
                    "area": bbox[2] * bbox[3],
                    "iscrowd": 0,
                    "track_id": box.track_id,
                    "team": box.team,
                    "jersey_number": box.jersey_number,
                    "occluded": box.occluded,
                    "truncated": box.truncated,
                    "dataset_version": box.provenance.dataset_version,
                }
            )
            annotation_id += 1

        pose_annotations = []
        annotation_id = 1
        for pose in sorted(
            (item for item in poses if split_by_video_id[item.provenance.video_id] == split),
            key=lambda item: (
                item.provenance.video_id,
                item.rally_id,
                item.frame.frame_index,
                item.track_id,
            ),
        ):
            key = _frame_key(
                pose.provenance.video_id,
                pose.rally_id,
                pose.frame.frame_index,
            )
            width, height = image_size_by_video_id[key[0]]
            bbox = [
                pose.bbox.x * width,
                pose.bbox.y * height,
                pose.bbox.width * width,
                pose.bbox.height * height,
            ]
            points_by_name = {point.name: point for point in pose.keypoints}
            keypoints: list[float | int] = []
            labelled_count = 0
            for name in VOLLEY_SKELETON_KEYPOINTS:
                point = points_by_name.get(name)
                visibility = _coco_visibility(point.visibility) if point else 0
                if point and point.pixel is not None:
                    x, y = point.pixel.x, point.pixel.y
                else:
                    x, y = 0.0, 0.0
                keypoints.extend([x, y, visibility])
                labelled_count += int(visibility > 0)
            pose_annotations.append(
                {
                    "id": annotation_id,
                    "image_id": pose_image_id_by_key[key],
                    "category_id": 1,
                    "bbox": bbox,
                    "area": bbox[2] * bbox[3],
                    "iscrowd": 0,
                    "keypoints": keypoints,
                    "num_keypoints": labelled_count,
                    "track_id": pose.track_id,
                    "team": pose.team,
                    "dataset_version": pose.provenance.dataset_version,
                }
            )
            annotation_id += 1

        ball_manifest = []
        for ball in sorted(
            (item for item in ball_frames if split_by_video_id[item.provenance.video_id] == split),
            key=lambda item: (
                item.provenance.video_id,
                item.rally_id,
                item.frame.frame_index,
            ),
        ):
            key = _frame_key(
                ball.provenance.video_id,
                ball.rally_id,
                ball.frame.frame_index,
            )
            ball_manifest.append(
                {
                    "image_id": ball_image_id_by_key[key],
                    "file_name": _file_name(key),
                    "video_id": key[0],
                    "rally_id": key[1],
                    "frame_index": key[2],
                    "timestamp_seconds": ball.frame.timestamp_seconds,
                    "visibility": ball.visibility,
                    "center_pixel": ball.center_pixel.model_dump() if ball.center_pixel else None,
                    "radius_px": ball.radius_px,
                    "motion_blurred": ball.motion_blurred,
                    "truncated": ball.truncated,
                    "dataset_version": ball.provenance.dataset_version,
                }
            )

        edge_indexes = [
            [VOLLEY_SKELETON_KEYPOINTS.index(start) + 1, VOLLEY_SKELETON_KEYPOINTS.index(end) + 1]
            for start, end in VOLLEY_SKELETON_EDGES
        ]
        exports[split] = {
            "player_detection_coco": {
                "info": {
                    "description": "Volley Intelligence reviewed person-role detections",
                    "split": split,
                },
                "images": detection_images,
                "annotations": detection_annotations,
                "categories": [
                    {
                        "id": index,
                        "name": role,
                        "supercategory": "person",
                    }
                    for index, role in enumerate(PERSON_ROLES, start=1)
                ],
            },
            "player_pose_coco": {
                "info": {
                    "description": "Volley Intelligence reviewed player/pose labels",
                    "split": split,
                },
                "images": pose_images,
                "annotations": pose_annotations,
                "categories": [
                    {
                        "id": 1,
                        "name": "on_court_player",
                        "supercategory": "person",
                        "keypoints": list(VOLLEY_SKELETON_KEYPOINTS),
                        "skeleton": edge_indexes,
                    }
                ],
            },
            "ball_frames": ball_manifest,
        }
    return exports


def write_training_exports(output_dir: Path, exports: dict[str, dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for split, payload in exports.items():
        (output_dir / f"players_detection_{split}.coco.json").write_text(
            json.dumps(payload["player_detection_coco"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / f"players_pose_{split}.coco.json").write_text(
            json.dumps(payload["player_pose_coco"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with (output_dir / f"ball_frames_{split}.jsonl").open("w", encoding="utf-8") as target:
            for record in payload["ball_frames"]:
                target.write(json.dumps(record, sort_keys=True) + "\n")


def _load_jsonl(path: Path, model: type[ModelT]) -> list[ModelT]:
    return [
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player-boxes", type=Path, required=True)
    parser.add_argument("--poses", type=Path, required=True)
    parser.add_argument("--ball-frames", type=Path, required=True)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--image-sizes", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    split = json.loads(args.split.read_text(encoding="utf-8"))["split_by_video_id"]
    raw_sizes = json.loads(args.image_sizes.read_text(encoding="utf-8"))
    image_sizes = {video_id: tuple(size) for video_id, size in raw_sizes.items()}
    exports = build_training_exports(
        _load_jsonl(args.poses, PlayerPoseFrameAnnotation),
        _load_jsonl(args.ball_frames, BallFrameAnnotation),
        player_boxes=_load_jsonl(args.player_boxes, PlayerBBoxAnnotation),
        split_by_video_id=split,
        image_size_by_video_id=image_sizes,
    )
    write_training_exports(args.out_dir, exports)
    print(f"Wrote deterministic training exports for {len(exports)} splits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
