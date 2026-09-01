import pytest
from volley_domain.annotation import BoundingBox, PixelPoint
from volley_domain.ontology import ActionType

from volley_ml.evaluation.volleyball import (
    BallPrediction,
    BallTarget,
    ContactPrediction,
    ContactTarget,
    DetectionPrediction,
    DetectionTarget,
    bbox_iou,
    evaluate_ball,
    evaluate_contacts,
    evaluate_detection,
)


def test_detection_ap_and_slice_are_exact_for_simple_fixture():
    targets = [
        DetectionTarget(
            target_id="a",
            video_id="v1",
            frame_index=1,
            category="player",
            bbox=BoundingBox(x=0.1, y=0.1, width=0.2, height=0.4),
            slice_tags={"venue-a"},
        ),
        DetectionTarget(
            target_id="b",
            video_id="v2",
            frame_index=1,
            category="player",
            bbox=BoundingBox(x=0.5, y=0.1, width=0.2, height=0.4),
            slice_tags={"venue-b"},
        ),
    ]
    predictions = [
        DetectionPrediction(
            prediction_id="p1",
            video_id="v1",
            frame_index=1,
            category="player",
            bbox=targets[0].bbox,
            confidence=0.9,
        )
    ]
    overall = evaluate_detection(targets, predictions)
    assert overall.precision == 1
    assert overall.recall == 0.5
    assert overall.average_precision == 0.5
    venue_a = evaluate_detection(targets, predictions, slice_tag="venue-a")
    assert venue_a.f1 == 1
    assert venue_a.average_precision == 1


def test_bbox_iou_handles_overlap_and_disjoint_boxes():
    box = BoundingBox(x=0.1, y=0.1, width=0.2, height=0.2)
    assert bbox_iou(box, box) == 1
    assert bbox_iou(box, BoundingBox(x=0.7, y=0.7, width=0.1, height=0.1)) == 0


def test_ball_metrics_measure_localization_and_gap_recovery():
    targets = [
        BallTarget(
            video_id="v1",
            rally_id="r1",
            frame_index=frame,
            visibility="visible" if frame in {1, 5} else "occluded",
            center_pixel=PixelPoint(x=10 * frame, y=20) if frame in {1, 5} else None,
        )
        for frame in range(1, 6)
    ]
    predictions = [
        BallPrediction(
            video_id="v1",
            rally_id="r1",
            frame_index=frame,
            visible_probability=0.9 if frame in {1, 5} else 0.1,
            center_pixel=PixelPoint(x=10 * frame + 3, y=24) if frame in {1, 5} else None,
        )
        for frame in range(1, 6)
    ]
    report = evaluate_ball(targets, predictions)
    assert report.visible_f1 == 1
    assert report.localization_rmse_px == pytest.approx(5)
    assert report.localization_mae_px == pytest.approx(5)
    assert report.occlusion_gap_targets_3_to_10 == 1
    assert report.gap_recovery_recall_3_to_10 == 1


def test_contact_metrics_separate_detection_actor_and_action_quality():
    targets = [
        ContactTarget(
            contact_id="c1",
            video_id="v1",
            rally_id="r1",
            frame_index=10,
            actor_track_id="server",
            action_type=ActionType.SERVE,
        ),
        ContactTarget(
            contact_id="c2",
            video_id="v1",
            rally_id="r1",
            frame_index=20,
            actor_track_id="receiver",
            action_type=ActionType.RECEPTION,
        ),
    ]
    predictions = [
        ContactPrediction(
            prediction_id="p1",
            video_id="v1",
            rally_id="r1",
            frame_index=11,
            actor_track_id="server",
            action_type=ActionType.SERVE,
            confidence=0.9,
        ),
        ContactPrediction(
            prediction_id="p2",
            video_id="v1",
            rally_id="r1",
            frame_index=20,
            actor_track_id="wrong-player",
            action_type=ActionType.DIG,
            confidence=0.8,
        ),
    ]
    report = evaluate_contacts(targets, predictions)
    assert report.contact_f1 == 1
    assert report.temporal_mae_frames == 0.5
    assert report.actor_accuracy == 0.5
    assert report.action_accuracy == 0.5
    assert report.action_macro_f1 == pytest.approx(1 / 3)
