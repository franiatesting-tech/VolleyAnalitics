"""Auditable detection, ball and contact metrics with explicit slice support."""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from pydantic import BaseModel, Field, model_validator
from volley_domain.annotation import BoundingBox, PixelPoint
from volley_domain.ontology import ActionType


class DetectionTarget(BaseModel):
    target_id: str
    video_id: str
    frame_index: int = Field(ge=0)
    category: str
    bbox: BoundingBox
    slice_tags: set[str] = Field(default_factory=set)


class DetectionPrediction(BaseModel):
    prediction_id: str
    video_id: str
    frame_index: int = Field(ge=0)
    category: str
    bbox: BoundingBox
    confidence: float = Field(ge=0, le=1)


class DetectionMetrics(BaseModel):
    iou_threshold: float
    target_count: int
    prediction_count: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    average_precision: float


class BallTarget(BaseModel):
    video_id: str
    rally_id: str
    frame_index: int = Field(ge=0)
    visibility: str
    center_pixel: PixelPoint | None = None
    slice_tags: set[str] = Field(default_factory=set)

    @model_validator(mode="after")
    def _visible_has_center(self) -> BallTarget:
        if self.visibility == "visible" and self.center_pixel is None:
            raise ValueError("visible ball target requires center_pixel")
        return self


class BallPrediction(BaseModel):
    video_id: str
    rally_id: str
    frame_index: int = Field(ge=0)
    visible_probability: float = Field(ge=0, le=1)
    center_pixel: PixelPoint | None = None


class BallMetrics(BaseModel):
    frame_count: int
    visible_targets: int
    true_positives: int
    false_positives: int
    false_negatives: int
    visible_precision: float
    visible_recall: float
    visible_f1: float
    localization_rmse_px: float | None
    localization_mae_px: float | None
    occlusion_gap_targets_3_to_10: int
    gap_recovery_recall_3_to_10: float | None


class ContactTarget(BaseModel):
    contact_id: str
    video_id: str
    rally_id: str
    frame_index: int = Field(ge=0)
    actor_track_id: str
    action_type: ActionType
    slice_tags: set[str] = Field(default_factory=set)


class ContactPrediction(BaseModel):
    prediction_id: str
    video_id: str
    rally_id: str
    frame_index: int = Field(ge=0)
    actor_track_id: str
    action_type: ActionType
    confidence: float = Field(ge=0, le=1)


class ContactMetrics(BaseModel):
    tolerance_frames: int
    target_count: int
    prediction_count: int
    matched_contacts: int
    contact_precision: float
    contact_recall: float
    contact_f1: float
    temporal_mae_frames: float | None
    actor_accuracy: float | None
    action_accuracy: float | None
    action_macro_f1: float | None


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def bbox_iou(left: BoundingBox, right: BoundingBox) -> float:
    left_x2, left_y2 = left.x + left.width, left.y + left.height
    right_x2, right_y2 = right.x + right.width, right.y + right.height
    intersection_width = max(0.0, min(left_x2, right_x2) - max(left.x, right.x))
    intersection_height = max(0.0, min(left_y2, right_y2) - max(left.y, right.y))
    intersection = intersection_width * intersection_height
    union = left.width * left.height + right.width * right.height - intersection
    return min(max(intersection / union, 0.0), 1.0) if union else 0.0


def evaluate_detection(
    targets: list[DetectionTarget],
    predictions: list[DetectionPrediction],
    *,
    iou_threshold: float = 0.5,
    slice_tag: str | None = None,
) -> DetectionMetrics:
    selected_targets = [
        target for target in targets if slice_tag is None or slice_tag in target.slice_tags
    ]
    evaluation_frames = {(target.video_id, target.frame_index) for target in selected_targets}
    selected_predictions = [
        prediction
        for prediction in predictions
        if (prediction.video_id, prediction.frame_index) in evaluation_frames
    ]
    targets_by_frame_category: dict[tuple[str, int, str], list[DetectionTarget]] = defaultdict(list)
    for target in selected_targets:
        targets_by_frame_category[(target.video_id, target.frame_index, target.category)].append(
            target
        )

    matched: set[str] = set()
    outcomes: list[int] = []
    for prediction in sorted(selected_predictions, key=lambda item: item.confidence, reverse=True):
        candidates = [
            target
            for target in targets_by_frame_category[
                (prediction.video_id, prediction.frame_index, prediction.category)
            ]
            if target.target_id not in matched
        ]
        best = max(
            candidates, key=lambda target: bbox_iou(prediction.bbox, target.bbox), default=None
        )
        if best is not None and bbox_iou(prediction.bbox, best.bbox) >= iou_threshold:
            matched.add(best.target_id)
            outcomes.append(1)
        else:
            outcomes.append(0)

    tp = sum(outcomes)
    fp = len(outcomes) - tp
    fn = len(selected_targets) - tp
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)

    if not selected_targets or not outcomes:
        average_precision = 0.0
    else:
        cumulative_tp = np.cumsum(outcomes)
        cumulative_fp = np.cumsum([1 - outcome for outcome in outcomes])
        precisions = cumulative_tp / np.maximum(cumulative_tp + cumulative_fp, 1)
        recalls = cumulative_tp / len(selected_targets)
        padded_precision = np.concatenate(([0.0], precisions, [0.0]))
        padded_recall = np.concatenate(([0.0], recalls, [1.0]))
        for index in range(len(padded_precision) - 2, -1, -1):
            padded_precision[index] = max(padded_precision[index], padded_precision[index + 1])
        changes = np.where(padded_recall[1:] != padded_recall[:-1])[0]
        average_precision = float(
            np.sum(
                (padded_recall[changes + 1] - padded_recall[changes])
                * padded_precision[changes + 1]
            )
        )

    return DetectionMetrics(
        iou_threshold=iou_threshold,
        target_count=len(selected_targets),
        prediction_count=len(selected_predictions),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
        average_precision=average_precision,
    )


def evaluate_ball(
    targets: list[BallTarget],
    predictions: list[BallPrediction],
    *,
    visibility_threshold: float = 0.5,
    slice_tag: str | None = None,
) -> BallMetrics:
    selected_targets = [
        target for target in targets if slice_tag is None or slice_tag in target.slice_tags
    ]
    predictions_by_key = {
        (prediction.video_id, prediction.rally_id, prediction.frame_index): prediction
        for prediction in predictions
    }
    tp = fp = fn = 0
    localization_errors = []
    for target in selected_targets:
        prediction = predictions_by_key.get((target.video_id, target.rally_id, target.frame_index))
        target_visible = target.visibility == "visible"
        predicted_visible = bool(
            prediction
            and prediction.visible_probability >= visibility_threshold
            and prediction.center_pixel is not None
        )
        if target_visible and predicted_visible:
            tp += 1
            assert target.center_pixel is not None
            assert prediction is not None and prediction.center_pixel is not None
            localization_errors.append(
                math.hypot(
                    target.center_pixel.x - prediction.center_pixel.x,
                    target.center_pixel.y - prediction.center_pixel.y,
                )
            )
        elif target_visible:
            fn += 1
        elif predicted_visible:
            fp += 1

    gap_targets = gap_recovered = 0
    by_rally: dict[tuple[str, str], list[BallTarget]] = defaultdict(list)
    for target in selected_targets:
        by_rally[(target.video_id, target.rally_id)].append(target)
    for rally_targets in by_rally.values():
        gap_length = 0
        for target in sorted(rally_targets, key=lambda item: item.frame_index):
            if target.visibility != "visible":
                gap_length += 1
                continue
            if 3 <= gap_length <= 10:
                gap_targets += 1
                prediction = predictions_by_key.get(
                    (target.video_id, target.rally_id, target.frame_index)
                )
                if (
                    prediction
                    and prediction.visible_probability >= visibility_threshold
                    and prediction.center_pixel is not None
                ):
                    gap_recovered += 1
            gap_length = 0

    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    return BallMetrics(
        frame_count=len(selected_targets),
        visible_targets=sum(target.visibility == "visible" for target in selected_targets),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        visible_precision=precision,
        visible_recall=recall,
        visible_f1=_f1(precision, recall),
        localization_rmse_px=(
            float(np.sqrt(np.mean(np.square(localization_errors)))) if localization_errors else None
        ),
        localization_mae_px=(float(np.mean(localization_errors)) if localization_errors else None),
        occlusion_gap_targets_3_to_10=gap_targets,
        gap_recovery_recall_3_to_10=(_ratio(gap_recovered, gap_targets) if gap_targets else None),
    )


def _macro_f1(targets: list[ActionType], predictions: list[ActionType]) -> float | None:
    if not targets:
        return None
    labels = sorted(set(targets) | set(predictions), key=lambda item: item.value)
    values = []
    for label in labels:
        tp = sum(t == label and p == label for t, p in zip(targets, predictions, strict=True))
        fp = sum(t != label and p == label for t, p in zip(targets, predictions, strict=True))
        fn = sum(t == label and p != label for t, p in zip(targets, predictions, strict=True))
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        values.append(_f1(precision, recall))
    return float(np.mean(values))


def evaluate_contacts(
    targets: list[ContactTarget],
    predictions: list[ContactPrediction],
    *,
    tolerance_frames: int = 1,
    slice_tag: str | None = None,
) -> ContactMetrics:
    selected_targets = [
        target for target in targets if slice_tag is None or slice_tag in target.slice_tags
    ]
    rally_keys = {(target.video_id, target.rally_id) for target in selected_targets}
    selected_predictions = [
        prediction
        for prediction in predictions
        if (prediction.video_id, prediction.rally_id) in rally_keys
    ]
    targets_by_rally: dict[tuple[str, str], list[ContactTarget]] = defaultdict(list)
    for target in selected_targets:
        targets_by_rally[(target.video_id, target.rally_id)].append(target)

    matched_ids: set[str] = set()
    matches: list[tuple[ContactTarget, ContactPrediction]] = []
    for prediction in sorted(selected_predictions, key=lambda item: item.confidence, reverse=True):
        candidates = [
            target
            for target in targets_by_rally[(prediction.video_id, prediction.rally_id)]
            if target.contact_id not in matched_ids
            and abs(target.frame_index - prediction.frame_index) <= tolerance_frames
        ]
        best = min(
            candidates,
            key=lambda target: abs(target.frame_index - prediction.frame_index),
            default=None,
        )
        if best is not None:
            matched_ids.add(best.contact_id)
            matches.append((best, prediction))

    matched = len(matches)
    precision = _ratio(matched, len(selected_predictions))
    recall = _ratio(matched, len(selected_targets))
    action_targets = [target.action_type for target, _ in matches]
    action_predictions = [prediction.action_type for _, prediction in matches]
    return ContactMetrics(
        tolerance_frames=tolerance_frames,
        target_count=len(selected_targets),
        prediction_count=len(selected_predictions),
        matched_contacts=matched,
        contact_precision=precision,
        contact_recall=recall,
        contact_f1=_f1(precision, recall),
        temporal_mae_frames=(
            float(np.mean([abs(t.frame_index - p.frame_index) for t, p in matches]))
            if matches
            else None
        ),
        actor_accuracy=(
            _ratio(
                sum(t.actor_track_id == p.actor_track_id for t, p in matches),
                matched,
            )
            if matched
            else None
        ),
        action_accuracy=(
            _ratio(
                sum(t == p for t, p in zip(action_targets, action_predictions, strict=True)),
                matched,
            )
            if matched
            else None
        ),
        action_macro_f1=_macro_f1(action_targets, action_predictions),
    )
