"""Build a deterministic, risk-based human review queue for model proposals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from volley_domain.preannotation import (
    BallFramePreannotation,
    ContactPreannotation,
    PlayerPosePreannotation,
    PlayerTrackPreannotation,
    Preannotation,
)

CRITICAL_POSE_POINTS = {"left_wrist", "right_wrist", "left_ankle", "right_ankle"}


class ReviewQueueItem(BaseModel):
    candidate_id: str
    signal_type: Literal["player_track", "ball_frame", "player_pose", "contact"]
    video_id: str
    frame_index: int = Field(ge=0)
    priority: float = Field(ge=0, le=100)
    reasons: list[str] = Field(min_length=1)


def _priority(item: Preannotation) -> tuple[float, list[str]]:
    reasons: list[str] = []
    if isinstance(item, ContactPreannotation):
        priority = 90.0
        reasons.append("all contact candidates require frame-and-actor review")
        if item.temporal_uncertainty_frames > 0:
            priority += min(5.0, float(item.temporal_uncertainty_frames))
            reasons.append("contact frame is temporally uncertain")
        weakest = min(item.confidence, item.actor_confidence, item.action_confidence)
        if weakest < 0.8:
            priority += min(5.0, (0.8 - weakest) * 25.0)
            reasons.append("contact, actor or action confidence is low")
        return min(priority, 100.0), reasons

    if isinstance(item, BallFramePreannotation):
        priority = 55.0 + (1.0 - item.confidence) * 25.0
        reasons.append("ball labels require frame-level review")
        ambiguity = 1.0 - abs(item.visible_probability - 0.5) * 2.0
        if ambiguity > 0.5:
            priority += ambiguity * 15.0
            reasons.append("ball visibility is ambiguous")
        if item.temporal_source != "observed":
            priority += 5.0
            reasons.append("ball location comes from temporal interpolation/prediction")
        return min(priority, 100.0), reasons

    if isinstance(item, PlayerPosePreannotation):
        priority = 35.0 + (1.0 - item.confidence) * 25.0
        reasons.append("pose requires anatomical review")
        critical_scores = [
            point.confidence for point in item.keypoints if point.name in CRITICAL_POSE_POINTS
        ]
        if critical_scores and min(critical_scores) < 0.7:
            priority += 20.0
            reasons.append("wrist or ankle confidence is low")
        return min(priority, 100.0), reasons

    if isinstance(item, PlayerTrackPreannotation):
        priority = 20.0 + (1.0 - item.confidence) * 30.0
        reasons.append("player track requires identity and box review")
        if item.person_role is None:
            priority += 10.0
            reasons.append("generic person detector did not assign an on-court role")
        if item.team_confidence is not None and item.team_confidence < 0.75:
            priority += 15.0
            reasons.append("team assignment confidence is low")
        if item.jersey_color_outlier:
            priority += 20.0
            reasons.append(
                "jersey color is a visual outlier vs. both majority team clusters -- "
                "check for libero, official, or a non-person false detection"
            )
        return min(priority, 100.0), reasons

    raise TypeError(f"unsupported preannotation type: {type(item)!r}")


def build_review_queue(items: list[Preannotation]) -> list[ReviewQueueItem]:
    candidate_ids = [item.candidate_id for item in items]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("preannotation candidate_id values must be unique")

    queue = []
    for item in items:
        if item.review.status != "unreviewed":
            continue
        priority, reasons = _priority(item)
        queue.append(
            ReviewQueueItem(
                candidate_id=item.candidate_id,
                signal_type=item.signal_type,
                video_id=item.provenance.video_id,
                frame_index=item.frame.frame_index,
                priority=round(priority, 3),
                reasons=reasons,
            )
        )
    return sorted(
        queue,
        key=lambda item: (
            -item.priority,
            item.video_id,
            item.frame_index,
            item.signal_type,
            item.candidate_id,
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    model_by_signal = {
        "player_track": PlayerTrackPreannotation,
        "ball_frame": BallFramePreannotation,
        "player_pose": PlayerPosePreannotation,
        "contact": ContactPreannotation,
    }
    items: list[Preannotation] = []
    for line in args.predictions.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        model = model_by_signal.get(payload.get("signal_type"))
        if model is None:
            raise ValueError(f"unknown signal_type: {payload.get('signal_type')!r}")
        items.append(model.model_validate(payload))

    queue = build_review_queue(items)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps([item.model_dump(mode="json") for item in queue], indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Queued {len(queue)} unreviewed model proposals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
