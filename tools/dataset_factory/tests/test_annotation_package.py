import pytest
from dataset_factory.annotation_package import build_annotation_package


def _inventory() -> dict:
    return {
        "plan_version": "golden-v0",
        "generated_at": "2026-08-30T12:00:00Z",
        "rights_source_id": "owner-authorized-source",
        "clips": [
            {
                "clip_id": "clip-a",
                "file_name": "clip-a.mp4",
                "sha256": "a" * 64,
                "source_video_id": "source-a",
                "source_url": "https://example.test/source-a",
                "title": "A vs B",
                "segment_start_seconds": 120.0,
                "segment_end_seconds": 180.0,
                "teams": ["A", "B"],
                "competition": "Cup",
                "court_group": "court-a",
                "sample_role": "active_play",
                "probe": {
                    "width": 1280,
                    "height": 720,
                    "fps": 50.0,
                    "duration_seconds": 60.0,
                },
            },
            {
                "clip_id": "clip-b",
                "file_name": "clip-b.mp4",
                "sha256": "b" * 64,
                "source_video_id": "source-b",
                "source_url": "https://example.test/source-b",
                "title": "C vs D",
                "segment_start_seconds": 240.0,
                "segment_end_seconds": 300.0,
                "teams": ["C", "D"],
                "competition": "Cup",
                "court_group": "court-b",
                "sample_role": "transition_negative",
                "probe": {
                    "width": 1280,
                    "height": 720,
                    "fps": 50.0,
                    "duration_seconds": 60.0,
                },
            },
        ],
    }


def test_annotation_package_freezes_media_split_and_scope():
    package = build_annotation_package(
        _inventory(),
        {"split_by_video_id": {"clip-a": "train", "clip-b": "test"}},
    )

    assert len(package["tasks"]) == 2
    active, negative = package["tasks"]
    assert active["media_sha256"] == "a" * 64
    assert active["source_segment_start_seconds"] == 120.0
    assert active["split"] == "train"
    assert active["video"]["estimated_frame_count"] == 3000
    assert "ball_points" in active["annotation_scope"]
    assert "pose_keypoints" in active["annotation_scope"]
    assert "ball_contacts" in active["annotation_scope"]
    assert "negative_review" in negative["annotation_scope"]
    assert package["rights_source_id"] == "owner-authorized-source"
    assert {label["name"] for label in package["labels"]} >= {
        "player",
        "ball",
        "court_keypoint",
        "rally",
        "pose_keypoint",
        "ball_contact",
        "biomechanics_phase",
    }


def test_annotation_package_rejects_unassigned_clip():
    with pytest.raises(ValueError, match="clips lack split assignment: clip-b"):
        build_annotation_package(
            _inventory(),
            {"split_by_video_id": {"clip-a": "train"}},
        )
