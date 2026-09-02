from datetime import UTC, datetime

from dataset_factory.professional_signal_qa import run_professional_signal_qa
from volley_domain.annotation import (
    BallContactAnnotation,
    BallFrameAnnotation,
    BoundingBox,
    CameraCalibrationAnnotation,
    FrameRef,
    GroundTruthProvenance,
    PixelPoint,
    PlayerBBoxAnnotation,
    PlayerPoseFrameAnnotation,
    PoseKeypointMeasurement,
    RallyGroundTruth,
)
from volley_domain.ontology import ActionType


def _provenance() -> GroundTruthProvenance:
    return GroundTruthProvenance(
        organization_id="org-1",
        video_id="video-1",
        video_hash="a" * 64,
        dataset_version="golden-v1",
        annotator_id="reviewer-1",
        source_tool="cvat",
        created_at=datetime.now(UTC),
        reviewed=True,
    )


def _contact(index: int, frame: int, action: ActionType, actor: str) -> BallContactAnnotation:
    return BallContactAnnotation(
        provenance=_provenance(),
        contact_id=f"contact-{index}",
        rally_id="rally-1",
        contact_index=index,
        frame=FrameRef(frame_index=frame, timestamp_seconds=frame / 50),
        team="home" if index == 1 else "away",
        actor_track_id=actor,
        action_type=action,
        ball_center_pixel=PixelPoint(x=600 + index, y=300),
    )


def _fixture():
    contacts = [
        _contact(1, 10, ActionType.SERVE, "server"),
        _contact(2, 15, ActionType.RECEPTION, "receiver"),
    ]
    rally = RallyGroundTruth(
        provenance=_provenance(),
        rally_id="rally-1",
        set_index=1,
        rally_index_in_set=1,
        start_frame=FrameRef(frame_index=10, timestamp_seconds=0.2),
        end_frame=FrameRef(frame_index=15, timestamp_seconds=0.3),
        serving_team="home",
        score_before_home=0,
        score_before_away=0,
        contacts=contacts,
    )
    balls = [
        BallFrameAnnotation(
            provenance=_provenance(),
            frame=FrameRef(frame_index=frame, timestamp_seconds=frame / 50),
            rally_id="rally-1",
            visibility="visible",
            center_pixel=PixelPoint(
                x=601 if frame == 10 else 602 if frame == 15 else 600,
                y=300,
            ),
        )
        for frame in range(10, 16)
    ]
    required_names = (
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
    )
    poses = [
        PlayerPoseFrameAnnotation(
            provenance=_provenance(),
            frame=contact.frame,
            rally_id="rally-1",
            track_id=contact.actor_track_id,
            team=contact.team,
            bbox=BoundingBox(x=0.1, y=0.1, width=0.2, height=0.6),
            keypoints=[
                PoseKeypointMeasurement(
                    name=name,
                    visibility="visible",
                    pixel=PixelPoint(x=500, y=300),
                )
                for name in required_names
            ],
        )
        for contact in contacts
    ]
    identity = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    calibration = CameraCalibrationAnnotation(
        provenance=_provenance(),
        calibration_id="calibration-1",
        frame=FrameRef(frame_index=0, timestamp_seconds=0),
        image_width=1280,
        image_height=720,
        net_height_m=2.24,
        calibration_mode="manual",
        homography_image_to_court=identity,
        labelled_keypoint_count=10,
        reprojection_error_px=1.0,
        confidence=0.95,
    )
    boxes = [
        PlayerBBoxAnnotation(
            provenance=_provenance(),
            frame=FrameRef(frame_index=frame, timestamp_seconds=frame / 50),
            track_id=f"player-{player_index}",
            bbox=BoundingBox(x=0.01 * player_index, y=0.1, width=0.05, height=0.5),
            team="home" if player_index < 6 else "away",
        )
        for frame in (10, 15)
        for player_index in range(12)
    ]
    return [rally], balls, poses, [calibration], boxes


def test_clean_2d_signals_are_ready_but_do_not_claim_metric_3d():
    report = run_professional_signal_qa(*_fixture())
    assert report.is_clean
    assert report.readiness["court_calibration_2d"]
    assert report.readiness["player_detection_tracking_2d"]
    assert report.readiness["ball_tracking_2d"]
    assert report.readiness["contact_attribution"]
    assert report.readiness["pose_biomechanics_2d"]
    assert not report.readiness["metric_3d_reference"]
    assert any("metric 3D reference" in warning for warning in report.warnings)


def test_missing_contact_ball_and_pose_are_blocking_violations():
    rallies, balls, poses, calibrations, boxes = _fixture()
    balls = [ball for ball in balls if ball.frame.frame_index != 15]
    poses = [pose for pose in poses if pose.track_id != "receiver"]
    report = run_professional_signal_qa(rallies, balls, poses, calibrations, boxes)
    assert not report.is_clean
    assert any("contact-2 has no exact-frame ball" in item for item in report.violations)
    assert any("contact-2 has no exact-frame actor pose" in item for item in report.violations)


def test_pose_missing_critical_joint_is_rejected():
    rallies, balls, poses, calibrations, boxes = _fixture()
    poses[0].keypoints = [
        keypoint for keypoint in poses[0].keypoints if keypoint.name != "left_wrist"
    ]
    report = run_professional_signal_qa(rallies, balls, poses, calibrations, boxes)
    assert not report.is_clean
    assert any("left_wrist" in item for item in report.violations)


def test_missing_player_checkpoint_is_not_detection_ready():
    rallies, balls, poses, calibrations, boxes = _fixture()
    boxes = [
        box for box in boxes if not (box.frame.frame_index == 15 and box.track_id == "player-0")
    ]
    report = run_professional_signal_qa(rallies, balls, poses, calibrations, boxes)
    assert not report.is_clean
    assert not report.readiness["player_detection_tracking_2d"]
    assert any("has 11 on-court player boxes" in item for item in report.violations)
