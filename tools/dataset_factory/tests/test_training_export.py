from datetime import UTC, datetime

import pytest
from dataset_factory.training_export import build_training_exports
from volley_domain.annotation import (
    VOLLEY_SKELETON_KEYPOINTS,
    BallFrameAnnotation,
    BoundingBox,
    FrameRef,
    GroundTruthProvenance,
    PixelPoint,
    PlayerBBoxAnnotation,
    PlayerPoseFrameAnnotation,
    PoseKeypointMeasurement,
)


def _provenance(video_id: str) -> GroundTruthProvenance:
    return GroundTruthProvenance(
        organization_id="org-1",
        video_id=video_id,
        video_hash=("a" if video_id == "video-a" else "b") * 64,
        dataset_version="golden-v1",
        annotator_id="reviewer-1",
        source_tool="cvat",
        created_at=datetime.now(UTC),
        reviewed=True,
    )


def _pose(video_id: str, frame: int) -> PlayerPoseFrameAnnotation:
    return PlayerPoseFrameAnnotation(
        provenance=_provenance(video_id),
        frame=FrameRef(frame_index=frame, timestamp_seconds=frame / 50),
        rally_id=f"rally-{video_id}",
        track_id="track-1",
        team="home",
        bbox=BoundingBox(x=0.1, y=0.2, width=0.25, height=0.5),
        keypoints=[
            PoseKeypointMeasurement(
                name="left_wrist",
                visibility="visible",
                pixel=PixelPoint(x=100, y=200),
            ),
            PoseKeypointMeasurement(name="right_wrist", visibility="occluded"),
        ],
    )


def _ball(video_id: str, frame: int, visibility: str) -> BallFrameAnnotation:
    return BallFrameAnnotation(
        provenance=_provenance(video_id),
        frame=FrameRef(frame_index=frame, timestamp_seconds=frame / 50),
        rally_id=f"rally-{video_id}",
        visibility=visibility,
        center_pixel=PixelPoint(x=500, y=250) if visibility == "visible" else None,
        radius_px=4 if visibility == "visible" else None,
    )


def _box(
    video_id: str,
    frame: int,
    *,
    person_role: str = "on_court_player",
    reviewed: bool = True,
) -> PlayerBBoxAnnotation:
    provenance = _provenance(video_id).model_copy(update={"reviewed": reviewed})
    return PlayerBBoxAnnotation(
        provenance=provenance,
        frame=FrameRef(frame_index=frame, timestamp_seconds=frame / 50),
        track_id=f"track-{person_role}",
        bbox=BoundingBox(x=0.1, y=0.2, width=0.25, height=0.5),
        person_role=person_role,
    )


def test_export_is_deterministic_and_split_safe():
    exports = build_training_exports(
        [_pose("video-a", 10), _pose("video-b", 20)],
        [_ball("video-a", 10, "visible"), _ball("video-b", 20, "occluded")],
        player_boxes=[_box("video-a", 10), _box("video-b", 20)],
        split_by_video_id={"video-a": "train", "video-b": "test"},
        image_size_by_video_id={"video-a": (1280, 720), "video-b": (1280, 720)},
    )
    assert set(exports) == {"train", "test"}
    assert {image["video_id"] for image in exports["train"]["player_pose_coco"]["images"]} == {
        "video-a"
    }
    annotation = exports["train"]["player_pose_coco"]["annotations"][0]
    assert annotation["bbox"] == pytest.approx([128, 144, 320, 360])
    assert annotation["num_keypoints"] == 2
    left_wrist_index = VOLLEY_SKELETON_KEYPOINTS.index("left_wrist") * 3
    right_wrist_index = VOLLEY_SKELETON_KEYPOINTS.index("right_wrist") * 3
    assert annotation["keypoints"][left_wrist_index : left_wrist_index + 3] == [100, 200, 2]
    assert annotation["keypoints"][right_wrist_index : right_wrist_index + 3] == [0, 0, 1]


def test_ball_export_preserves_explicit_occlusion():
    exports = build_training_exports(
        [_pose("video-b", 20)],
        [_ball("video-b", 20, "occluded")],
        split_by_video_id={"video-b": "val"},
        image_size_by_video_id={"video-b": (1280, 720)},
    )
    ball = exports["val"]["ball_frames"][0]
    assert ball["visibility"] == "occluded"
    assert ball["center_pixel"] is None


def test_export_rejects_unassigned_video():
    with pytest.raises(ValueError, match="lack split assignment: video-a"):
        build_training_exports(
            [_pose("video-a", 10)],
            [],
            split_by_video_id={},
            image_size_by_video_id={"video-a": (1280, 720)},
        )


def test_detection_export_preserves_person_role_and_track():
    exports = build_training_exports(
        [],
        [],
        player_boxes=[_box("video-a", 10, person_role="official")],
        split_by_video_id={"video-a": "train"},
        image_size_by_video_id={"video-a": (1280, 720)},
    )
    detection = exports["train"]["player_detection_coco"]["annotations"][0]
    assert detection["category_id"] == 3
    assert detection["track_id"] == "track-official"


def test_signal_specific_image_catalogs_do_not_create_false_negatives():
    exports = build_training_exports(
        [_pose("video-a", 20)],
        [_ball("video-a", 30, "visible")],
        player_boxes=[_box("video-a", 10)],
        split_by_video_id={"video-a": "train"},
        image_size_by_video_id={"video-a": (1280, 720)},
    )
    detection_frames = {
        image["frame_index"] for image in exports["train"]["player_detection_coco"]["images"]
    }
    pose_frames = {image["frame_index"] for image in exports["train"]["player_pose_coco"]["images"]}
    ball_frames = {item["frame_index"] for item in exports["train"]["ball_frames"]}
    assert detection_frames == {10}
    assert pose_frames == {20}
    assert ball_frames == {30}


def test_export_fails_closed_on_unreviewed_ground_truth():
    with pytest.raises(ValueError, match="player boxes contains 1 unreviewed labels"):
        build_training_exports(
            [],
            [],
            player_boxes=[_box("video-a", 10, reviewed=False)],
            split_by_video_id={"video-a": "train"},
            image_size_by_video_id={"video-a": (1280, 720)},
        )
