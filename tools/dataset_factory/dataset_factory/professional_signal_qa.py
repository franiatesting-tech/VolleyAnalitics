"""Cross-signal QA for rally, ball, pose, contact and calibration labels."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel
from volley_domain.annotation import (
    BallFrameAnnotation,
    CameraCalibrationAnnotation,
    PlayerBBoxAnnotation,
    PlayerPoseFrameAnnotation,
    RallyGroundTruth,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

CONTACT_POSE_KEYPOINTS = {
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
}


@dataclass
class ProfessionalSignalQAReport:
    rally_count: int
    contact_count: int
    ball_frame_count: int
    player_box_count: int
    pose_frame_count: int
    calibration_count: int
    ball_frame_coverage: float
    player_checkpoint_coverage: float
    contact_ball_link_fraction: float
    contact_actor_pose_link_fraction: float
    contact_critical_pose_fraction: float
    ball_world_3d_fraction: float
    triangulated_ball_fraction: float
    readiness: dict[str, bool]
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.violations

    def as_json(self) -> dict[str, Any]:
        return {**asdict(self), "is_clean": self.is_clean}


def _fraction(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def run_professional_signal_qa(
    rallies: list[RallyGroundTruth],
    ball_frames: list[BallFrameAnnotation],
    pose_frames: list[PlayerPoseFrameAnnotation],
    calibrations: list[CameraCalibrationAnnotation],
    player_boxes: list[PlayerBBoxAnnotation] | None = None,
) -> ProfessionalSignalQAReport:
    player_boxes = player_boxes or []
    violations: list[str] = []
    warnings: list[str] = []
    rally_by_id = {rally.rally_id: rally for rally in rallies}
    if len(rally_by_id) != len(rallies):
        violations.append("duplicate rally_id values")

    reviewed_groups = {
        "rallies": rallies,
        "ball frames": ball_frames,
        "player boxes": player_boxes,
        "pose frames": pose_frames,
        "calibrations": calibrations,
    }
    for signal_name, records in reviewed_groups.items():
        unreviewed = sum(not record.provenance.reviewed for record in records)
        if unreviewed:
            violations.append(f"{signal_name} contains {unreviewed} unreviewed labels")
    unreviewed_contacts = sum(
        not contact.provenance.reviewed for rally in rallies for contact in rally.contacts
    )
    if unreviewed_contacts:
        violations.append(f"contacts contains {unreviewed_contacts} unreviewed labels")

    ball_by_key: dict[tuple[str, int], BallFrameAnnotation] = {}
    for sample in ball_frames:
        key = (sample.rally_id, sample.frame.frame_index)
        if key in ball_by_key:
            violations.append(f"duplicate ball label for {key[0]} frame {key[1]}")
        ball_by_key[key] = sample
        rally = rally_by_id.get(sample.rally_id)
        if rally is None:
            violations.append(f"ball frame references unknown rally {sample.rally_id}")
        elif (
            not rally.start_frame.frame_index
            <= sample.frame.frame_index
            <= rally.end_frame.frame_index
        ):
            violations.append(
                f"ball frame {sample.frame.frame_index} lies outside rally {sample.rally_id}"
            )

    pose_by_key: dict[tuple[str, int, str], PlayerPoseFrameAnnotation] = {}
    for sample in pose_frames:
        key = (sample.rally_id, sample.frame.frame_index, sample.track_id)
        if key in pose_by_key:
            violations.append(f"duplicate pose label for {key[0]} frame {key[1]} track {key[2]}")
        pose_by_key[key] = sample
        if sample.rally_id not in rally_by_id:
            violations.append(f"pose frame references unknown rally {sample.rally_id}")

    player_by_key: dict[tuple[str, int, str], PlayerBBoxAnnotation] = {}
    on_court_count_by_frame: dict[tuple[str, int], int] = {}
    for sample in player_boxes:
        key = (sample.provenance.video_id, sample.frame.frame_index, sample.track_id)
        if key in player_by_key:
            violations.append(f"duplicate player box for {key[0]} frame {key[1]} track {key[2]}")
        player_by_key[key] = sample
        if sample.person_role == "on_court_player":
            frame_key = (sample.provenance.video_id, sample.frame.frame_index)
            on_court_count_by_frame[frame_key] = on_court_count_by_frame.get(frame_key, 0) + 1

    calibration_by_video: dict[str, list[CameraCalibrationAnnotation]] = {}
    for calibration in calibrations:
        calibration_by_video.setdefault(calibration.provenance.video_id, []).append(calibration)
        if calibration.reprojection_error_px > 3.0:
            warnings.append(
                f"calibration {calibration.calibration_id} exceeds 3 px reprojection error"
            )
        if calibration.confidence < 0.8:
            warnings.append(f"calibration {calibration.calibration_id} confidence is below 0.8")

    expected_ball_frames = sum(
        rally.end_frame.frame_index - rally.start_frame.frame_index + 1 for rally in rallies
    )
    expected_player_checkpoints = []
    valid_player_checkpoints = 0
    for rally in rallies:
        checkpoint_frames = list(
            range(rally.start_frame.frame_index, rally.end_frame.frame_index + 1, 5)
        )
        if checkpoint_frames[-1] != rally.end_frame.frame_index:
            checkpoint_frames.append(rally.end_frame.frame_index)
        for frame_index in checkpoint_frames:
            expected_player_checkpoints.append((rally.provenance.video_id, frame_index))
            player_count = on_court_count_by_frame.get((rally.provenance.video_id, frame_index), 0)
            if player_count == 12:
                valid_player_checkpoints += 1
            else:
                violations.append(
                    f"rally {rally.rally_id} frame {frame_index} has {player_count} "
                    "on-court player boxes; expected 12"
                )
    contact_count = sum(len(rally.contacts) for rally in rallies)
    linked_ball = 0
    linked_pose = 0
    complete_pose = 0

    for rally in rallies:
        if rally.provenance.video_id not in calibration_by_video:
            violations.append(f"rally {rally.rally_id} has no camera calibration")
        for contact in rally.contacts:
            ball = ball_by_key.get((rally.rally_id, contact.frame.frame_index))
            if ball is None:
                violations.append(
                    f"contact {contact.contact_id} has no exact-frame ball annotation"
                )
            else:
                linked_ball += 1
                if ball.center_pixel is not None:
                    distance = math.hypot(
                        ball.center_pixel.x - contact.ball_center_pixel.x,
                        ball.center_pixel.y - contact.ball_center_pixel.y,
                    )
                    if distance > 8.0:
                        violations.append(
                            f"contact {contact.contact_id} differs from ball label "
                            f"by {distance:.1f}px"
                        )

            pose = pose_by_key.get(
                (rally.rally_id, contact.frame.frame_index, contact.actor_track_id)
            )
            if pose is None:
                violations.append(f"contact {contact.contact_id} has no exact-frame actor pose")
                continue
            linked_pose += 1
            labelled = {
                keypoint.name
                for keypoint in pose.keypoints
                if keypoint.visibility in {"visible", "occluded"}
            }
            missing = sorted(CONTACT_POSE_KEYPOINTS - labelled)
            if missing:
                violations.append(
                    f"contact {contact.contact_id} actor pose misses: {', '.join(missing)}"
                )
            else:
                complete_pose += 1

    visible_balls = [sample for sample in ball_frames if sample.visibility == "visible"]
    world_balls = [sample for sample in visible_balls if sample.world_3d is not None]
    triangulated_balls = [
        sample
        for sample in world_balls
        if sample.world_3d and sample.world_3d.measurement_mode == "triangulated"
    ]

    ball_coverage = _fraction(len(ball_by_key), expected_ball_frames)
    player_checkpoint_coverage = _fraction(
        valid_player_checkpoints, len(expected_player_checkpoints)
    )
    contact_ball_fraction = _fraction(linked_ball, contact_count)
    contact_pose_fraction = _fraction(linked_pose, contact_count)
    critical_pose_fraction = _fraction(complete_pose, contact_count)
    ball_world_fraction = _fraction(len(world_balls), len(visible_balls))
    triangulated_fraction = _fraction(len(triangulated_balls), len(visible_balls))

    if ball_coverage < 0.98:
        violations.append(f"ball frame coverage {ball_coverage:.3f} is below 0.98")

    three_dimensional_calibrations = [
        calibration for calibration in calibrations if calibration.supports_metric_3d
    ]
    metric_3d_reference_ready = (
        triangulated_fraction >= 0.95
        and bool(three_dimensional_calibrations)
        and all(calibration.reprojection_error_px <= 3 for calibration in calibrations)
    )
    if not metric_3d_reference_ready:
        warnings.append(
            "metric 3D reference is not ready; use monocular values only as estimates "
            "with uncertainty until synchronized multi-camera labels exist"
        )

    contact_violations = [
        message
        for message in violations
        if message.startswith("contact ") or "pose misses" in message
    ]
    court_calibration_ready = bool(calibrations) and all(
        calibration.reprojection_error_px <= 3.0 and calibration.confidence >= 0.8
        for calibration in calibrations
    )
    readiness = {
        "court_calibration_2d": court_calibration_ready,
        "player_detection_tracking_2d": (
            bool(player_boxes)
            and player_checkpoint_coverage >= 0.98
            and not any(
                message.startswith("duplicate player box")
                or "on-court player boxes" in message
                or message.startswith("player boxes contains")
                for message in violations
            )
        ),
        "ball_tracking_2d": ball_coverage >= 0.98 and linked_ball == contact_count,
        "contact_attribution": contact_count > 0 and not contact_violations,
        "pose_biomechanics_2d": (
            contact_count > 0 and critical_pose_fraction >= 0.95 and linked_pose == contact_count
        ),
        "metric_3d_reference": metric_3d_reference_ready,
    }

    return ProfessionalSignalQAReport(
        rally_count=len(rallies),
        contact_count=contact_count,
        ball_frame_count=len(ball_frames),
        player_box_count=len(player_boxes),
        pose_frame_count=len(pose_frames),
        calibration_count=len(calibrations),
        ball_frame_coverage=ball_coverage,
        player_checkpoint_coverage=player_checkpoint_coverage,
        contact_ball_link_fraction=contact_ball_fraction,
        contact_actor_pose_link_fraction=contact_pose_fraction,
        contact_critical_pose_fraction=critical_pose_fraction,
        ball_world_3d_fraction=ball_world_fraction,
        triangulated_ball_fraction=triangulated_fraction,
        readiness=readiness,
        violations=violations,
        warnings=warnings,
    )


def _load_jsonl(path: Path, model: type[ModelT]) -> list[ModelT]:
    records: list[ModelT] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(model.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"{path}:{line_number}: {exc}") from exc
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rallies", type=Path, required=True)
    parser.add_argument("--ball-frames", type=Path, required=True)
    parser.add_argument("--player-boxes", type=Path, required=True)
    parser.add_argument("--pose-frames", type=Path, required=True)
    parser.add_argument("--calibrations", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    report = run_professional_signal_qa(
        _load_jsonl(args.rallies, RallyGroundTruth),
        _load_jsonl(args.ball_frames, BallFrameAnnotation),
        _load_jsonl(args.pose_frames, PlayerPoseFrameAnnotation),
        _load_jsonl(args.calibrations, CameraCalibrationAnnotation),
        _load_jsonl(args.player_boxes, PlayerBBoxAnnotation),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report.as_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.as_json(), indent=2, sort_keys=True))
    return 0 if report.is_clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
