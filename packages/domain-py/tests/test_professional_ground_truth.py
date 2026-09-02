from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from volley_domain.annotation import (
    BallContactAnnotation,
    BallFrameAnnotation,
    BoundingBox,
    CameraCalibrationAnnotation,
    FrameRef,
    GroundTruthProvenance,
    PixelPoint,
    PlayerPoseFrameAnnotation,
    PoseKeypointMeasurement,
    RallyGroundTruth,
    ScalarMeasurement,
    SpatialEstimate3D,
    WorldPoint3D,
    WorldUncertainty,
)
from volley_domain.ontology import ActionType


def _provenance() -> GroundTruthProvenance:
    return GroundTruthProvenance(
        organization_id="org-1",
        video_id="video-1",
        video_hash="a" * 64,
        dataset_version="golden-v1",
        annotator_id="annotator-1",
        source_tool="cvat",
        created_at=datetime.now(UTC),
        reviewed=True,
    )


def _spatial(*, mode: str = "monocular_physics", cameras: list[str] | None = None):
    return SpatialEstimate3D(
        point=WorldPoint3D(x_m=4.5, y_m=8.0, z_m=2.5),
        measurement_mode=mode,
        confidence=0.8,
        uncertainty=WorldUncertainty(x_std_m=0.1, y_std_m=0.2, z_std_m=0.4),
        reprojection_error_px=1.5,
        camera_ids=cameras or ["camera-a"],
        calibration_id="calibration-1",
    )


def _contact(index: int, team: str, action: ActionType) -> BallContactAnnotation:
    return BallContactAnnotation(
        provenance=_provenance(),
        contact_id=f"contact-{index}",
        rally_id="rally-1",
        contact_index=index,
        frame=FrameRef(frame_index=100 + index * 5, timestamp_seconds=2 + index * 0.1),
        team=team,
        actor_track_id=f"track-{team}-{index}",
        action_type=action,
        ball_center_pixel=PixelPoint(x=640, y=360),
    )


def test_triangulated_measurement_requires_two_distinct_cameras():
    with pytest.raises(ValidationError, match="at least two distinct cameras"):
        _spatial(mode="triangulated", cameras=["camera-a"])
    assert _spatial(mode="triangulated", cameras=["camera-a", "camera-b"])


def test_visible_ball_and_pose_keypoints_require_pixel_coordinates():
    with pytest.raises(ValidationError, match="visible ball requires"):
        BallFrameAnnotation(
            provenance=_provenance(),
            frame=FrameRef(frame_index=1, timestamp_seconds=0.02),
            rally_id="rally-1",
            visibility="visible",
        )
    with pytest.raises(ValidationError, match="visible pose keypoint requires"):
        PoseKeypointMeasurement(name="left_wrist", visibility="visible")


def test_pose_rejects_unknown_or_duplicate_keypoints():
    with pytest.raises(ValidationError, match="unknown volleyball skeleton"):
        PoseKeypointMeasurement(
            name="imaginary_joint",
            visibility="visible",
            pixel=PixelPoint(x=10, y=20),
        )

    keypoint = PoseKeypointMeasurement(
        name="left_wrist",
        visibility="visible",
        pixel=PixelPoint(x=10, y=20),
    )
    with pytest.raises(ValidationError, match="must be unique"):
        PlayerPoseFrameAnnotation(
            provenance=_provenance(),
            frame=FrameRef(frame_index=1, timestamp_seconds=0.02),
            rally_id="rally-1",
            track_id="track-1",
            team="home",
            bbox=BoundingBox(x=0.1, y=0.1, width=0.2, height=0.5),
            keypoints=[keypoint, keypoint],
        )


def test_metric_abstention_never_carries_a_fabricated_value():
    measurement = ScalarMeasurement(
        value=None,
        unit="m",
        measurement_mode="monocular_physics",
        confidence=0.1,
        status="abstained",
        abstention_reason="ball occluded at contact",
    )
    assert measurement.value is None

    with pytest.raises(ValidationError, match="no value and a reason"):
        ScalarMeasurement(
            value=3.2,
            unit="m",
            measurement_mode="monocular_physics",
            confidence=0.1,
            status="abstained",
            abstention_reason="ambiguous depth",
        )


def test_metric_3d_calibration_requires_intrinsics_and_extrinsics():
    matrix = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    with pytest.raises(ValidationError, match="requires intrinsics and extrinsics"):
        CameraCalibrationAnnotation(
            provenance=_provenance(),
            calibration_id="calibration-1",
            frame=FrameRef(frame_index=0, timestamp_seconds=0),
            image_width=1280,
            image_height=720,
            net_height_m=2.24,
            calibration_mode="manual",
            homography_image_to_court=matrix,
            labelled_keypoint_count=10,
            reprojection_error_px=1.0,
            confidence=0.95,
            supports_metric_3d=True,
        )


def test_complete_rally_starts_with_serve_and_enforces_three_contacts():
    with pytest.raises(ValidationError, match="must begin with a serve"):
        RallyGroundTruth(
            provenance=_provenance(),
            rally_id="rally-1",
            set_index=1,
            rally_index_in_set=1,
            start_frame=FrameRef(frame_index=100, timestamp_seconds=2.0),
            end_frame=FrameRef(frame_index=200, timestamp_seconds=4.0),
            serving_team="home",
            score_before_home=0,
            score_before_away=0,
            contacts=[_contact(1, "away", ActionType.RECEPTION)],
        )

    contacts = [
        _contact(1, "home", ActionType.SERVE),
        _contact(2, "away", ActionType.RECEPTION),
        _contact(3, "away", ActionType.SET),
        _contact(4, "away", ActionType.ATTACK),
        _contact(5, "away", ActionType.DIG),
    ]
    with pytest.raises(ValidationError, match="more than three counted team contacts"):
        RallyGroundTruth(
            provenance=_provenance(),
            rally_id="rally-1",
            set_index=1,
            rally_index_in_set=1,
            start_frame=FrameRef(frame_index=100, timestamp_seconds=2.0),
            end_frame=FrameRef(frame_index=200, timestamp_seconds=4.0),
            serving_team="home",
            score_before_home=0,
            score_before_away=0,
            contacts=contacts,
        )


def test_block_touch_does_not_consume_one_of_three_team_contacts():
    contacts = [
        _contact(1, "home", ActionType.SERVE),
        _contact(2, "away", ActionType.BLOCK),
        _contact(3, "away", ActionType.DIG),
        _contact(4, "away", ActionType.SET),
        _contact(5, "away", ActionType.ATTACK),
    ]
    rally = RallyGroundTruth(
        provenance=_provenance(),
        rally_id="rally-1",
        set_index=1,
        rally_index_in_set=1,
        start_frame=FrameRef(frame_index=100, timestamp_seconds=2.0),
        end_frame=FrameRef(frame_index=200, timestamp_seconds=4.0),
        serving_team="home",
        score_before_home=0,
        score_before_away=0,
        contacts=contacts,
    )
    assert len(rally.contacts) == 5


def test_transition_cannot_be_recorded_as_a_ball_contact():
    with pytest.raises(ValidationError, match="not a ball contact"):
        _contact(1, "home", ActionType.TRANSITION)
