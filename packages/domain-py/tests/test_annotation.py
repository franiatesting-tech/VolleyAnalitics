from datetime import UTC, datetime

import pytest
from volley_domain.annotation import (
    COURT_KEYPOINT_NAMES,
    BallAnnotation,
    BoundingBox,
    ConflictingTrackPositionError,
    FrameRef,
    GroundTruthProvenance,
    PlayerBBoxAnnotation,
    cvat_task_labels_config,
    fiftyone_detection_to_player_bbox,
    parse_cvat_video_xml,
    player_bbox_annotations_to_cvat_video_xml,
    player_bbox_to_fiftyone_detection,
    propagate_roster_position_by_track,
)
from volley_domain.ontology import RosterPosition


def _provenance(**overrides) -> GroundTruthProvenance:
    defaults = dict(
        organization_id="org-1",
        video_id="v1",
        video_hash="a" * 64,
        dataset_version="golden-v0",
        annotator_id="annotator-1",
        source_tool="cvat",
        created_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return GroundTruthProvenance(**defaults)


def test_provenance_requires_a_real_looking_video_hash():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _provenance(video_hash="too-short")


def test_bbox_cannot_extend_outside_the_normalized_frame():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="extends outside"):
        BoundingBox(x=0.9, y=0.1, width=0.2, height=0.2)


def test_cvat_task_labels_config_uses_the_real_ontology_taxonomy():
    labels = cvat_task_labels_config()
    names = {label["name"] for label in labels}
    assert names == {"player", "ball", "action"}

    player_label = next(label for label in labels if label["name"] == "player")
    position_attr = next(a for a in player_label["attributes"] if a["name"] == "position")
    assert set(position_attr["values"]) == {p.value for p in RosterPosition}


def test_cvat_task_labels_config_can_include_professional_signals():
    labels = cvat_task_labels_config(
        include_court=True,
        include_rallies=True,
        include_pose=True,
        include_contacts=True,
        include_biomechanics=True,
    )
    names = {label["name"] for label in labels}
    assert names == {
        "player",
        "ball",
        "action",
        "court_keypoint",
        "rally",
        "pose_keypoint",
        "ball_contact",
        "biomechanics_phase",
    }

    court_label = next(label for label in labels if label["name"] == "court_keypoint")
    keypoint_attr = next(
        attribute for attribute in court_label["attributes"] if attribute["name"] == "keypoint_name"
    )
    assert tuple(keypoint_attr["values"]) == COURT_KEYPOINT_NAMES

    pose_label = next(label for label in labels if label["name"] == "pose_keypoint")
    pose_names = next(
        attribute["values"]
        for attribute in pose_label["attributes"]
        if attribute["name"] == "keypoint_name"
    )
    assert "left_big_toe" in pose_names
    assert "right_heel" in pose_names


def test_player_bbox_cvat_round_trip():
    provenance = _provenance()
    original = [
        PlayerBBoxAnnotation(
            provenance=provenance,
            frame=FrameRef(frame_index=10, timestamp_seconds=0.4),
            track_id="track-1",
            bbox=BoundingBox(x=0.1, y=0.2, width=0.05, height=0.1),
            team="home",
            person_role="on_court_player",
            jersey_number=7,
            position=RosterPosition.OH,
            occluded=False,
            truncated=True,
        ),
        PlayerBBoxAnnotation(
            provenance=provenance,
            frame=FrameRef(frame_index=11, timestamp_seconds=0.44),
            track_id="track-1",
            bbox=BoundingBox(x=0.11, y=0.2, width=0.05, height=0.1),
            team="home",
            jersey_number=7,
            position=RosterPosition.OH,
            occluded=True,
        ),
    ]

    frame_width, frame_height = 1920.0, 1080.0
    xml_text = player_bbox_annotations_to_cvat_video_xml(
        original, frame_width=frame_width, frame_height=frame_height
    )
    assert "<track" in xml_text
    assert 'label="player"' in xml_text

    reparsed = parse_cvat_video_xml(
        xml_text,
        provenance=provenance,
        fps=25.0,
        frame_width=frame_width,
        frame_height=frame_height,
    )
    assert len(reparsed) == 2
    first, second = sorted(reparsed, key=lambda a: a.frame.frame_index)

    assert first.track_id == "track-1"
    assert first.team == "home"
    assert first.person_role == "on_court_player"
    assert first.truncated is True
    assert first.jersey_number == 7
    assert first.position == RosterPosition.OH
    assert first.occluded is False
    assert first.bbox.x == pytest.approx(0.1)
    assert first.bbox.width == pytest.approx(0.05)
    assert first.frame.timestamp_seconds == pytest.approx(10 / 25.0)

    assert second.occluded is True


def test_cvat_parse_normalizes_pixel_coordinates_against_frame_size():
    frame_width, frame_height = 100.0, 200.0
    xml_text = (
        '<annotations><track id="t1" label="player">'
        '<box frame="0" xtl="10" ytl="20" xbr="30" ybr="60" outside="0" occluded="0" keyframe="1"/>'
        "</track></annotations>"
    )
    parsed = parse_cvat_video_xml(
        xml_text,
        provenance=_provenance(),
        fps=30.0,
        frame_width=frame_width,
        frame_height=frame_height,
    )
    assert len(parsed) == 1
    ann = parsed[0]
    assert ann.bbox.x == pytest.approx(10 / 100)
    assert ann.bbox.y == pytest.approx(20 / 200)
    assert ann.bbox.width == pytest.approx(20 / 100)
    assert ann.bbox.height == pytest.approx(40 / 200)


def test_cvat_parse_skips_outside_boxes():
    xml_text = (
        '<annotations><track id="t1" label="player">'
        '<box frame="0" xtl="0" ytl="0" xbr="10" ybr="10" outside="0" occluded="0" keyframe="1"/>'
        '<box frame="1" xtl="0" ytl="0" xbr="10" ybr="10" outside="1" occluded="0" keyframe="1"/>'
        "</track></annotations>"
    )
    parsed = parse_cvat_video_xml(
        xml_text, provenance=_provenance(), fps=30.0, frame_width=100.0, frame_height=100.0
    )
    assert len(parsed) == 1
    assert parsed[0].frame.frame_index == 0


def test_fiftyone_detection_round_trip():
    provenance = _provenance(source_tool="fiftyone")
    original = PlayerBBoxAnnotation(
        provenance=provenance,
        frame=FrameRef(frame_index=5, timestamp_seconds=0.2),
        track_id="track-9",
        bbox=BoundingBox(x=0.25, y=0.3, width=0.1, height=0.2),
        team="away",
        jersey_number=12,
        position=RosterPosition.MB,
        occluded=False,
    )

    detection = player_bbox_to_fiftyone_detection(original)
    assert detection["_cls"] == "Detection"
    assert detection["bounding_box"] == [0.25, 0.3, 0.1, 0.2]
    assert detection["attributes"]["team"] == "away"
    assert detection["attributes"]["person_role"] == "on_court_player"

    round_tripped = fiftyone_detection_to_player_bbox(
        detection, provenance=provenance, frame=original.frame
    )
    assert round_tripped.track_id == "track-9"
    assert round_tripped.team == "away"
    assert round_tripped.person_role == "on_court_player"
    assert round_tripped.jersey_number == 12
    assert round_tripped.position == RosterPosition.MB
    assert round_tripped.bbox.x == pytest.approx(0.25)


def test_ball_annotation_allows_not_visible_with_no_coordinates():
    ann = BallAnnotation(
        provenance=_provenance(),
        frame=FrameRef(frame_index=0, timestamp_seconds=0.0),
        x_pixel=None,
        y_pixel=None,
        visible=False,
    )
    assert ann.visible is False


def test_visible_ball_requires_coordinates():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="requires x_pixel"):
        BallAnnotation(
            provenance=_provenance(),
            frame=FrameRef(frame_index=0, timestamp_seconds=0.0),
            x_pixel=None,
            y_pixel=None,
            visible=True,
        )


def _box_ann(*, track_id, frame_index, position=None, reviewed=False, video_id="v1"):
    return PlayerBBoxAnnotation(
        provenance=_provenance(video_id=video_id, reviewed=reviewed),
        frame=FrameRef(frame_index=frame_index, timestamp_seconds=frame_index / 30),
        track_id=track_id,
        bbox=BoundingBox(x=0.1, y=0.1, width=0.05, height=0.1),
        team="home",
        position=position,
    )


def test_propagate_roster_position_fills_in_unlabeled_frames_of_the_same_track():
    annotations = [
        _box_ann(track_id="t1", frame_index=0, position=RosterPosition.S, reviewed=True),
        _box_ann(track_id="t1", frame_index=1),
        _box_ann(track_id="t1", frame_index=2),
        _box_ann(track_id="t2", frame_index=0),  # different track, must stay unlabeled
    ]
    result = propagate_roster_position_by_track(annotations)
    by_frame = {ann.frame.frame_index: ann for ann in result if ann.track_id == "t1"}
    assert by_frame[0].position == RosterPosition.S
    assert by_frame[1].position == RosterPosition.S
    assert by_frame[2].position == RosterPosition.S
    other_track = next(ann for ann in result if ann.track_id == "t2")
    assert other_track.position is None


def test_propagate_roster_position_never_overwrites_an_already_labeled_frame():
    """Frame 1 already carries its own (unreviewed model-suggested)
    position -- propagation from frame 0's reviewed label must not
    clobber it, even though frame 1 has no reviewed label of its own yet."""
    annotations = [
        _box_ann(track_id="t1", frame_index=0, position=RosterPosition.S, reviewed=True),
        _box_ann(track_id="t1", frame_index=1, position=RosterPosition.MB, reviewed=False),
    ]
    result = propagate_roster_position_by_track(annotations)
    assert result[0].position == RosterPosition.S
    assert result[1].position == RosterPosition.MB


def test_propagate_roster_position_ignores_unreviewed_labels():
    """An unreviewed model-assisted guess must never fan out to other
    frames -- only a human-confirmed (reviewed=True) label may propagate."""
    annotations = [
        _box_ann(track_id="t1", frame_index=0, position=RosterPosition.S, reviewed=False),
        _box_ann(track_id="t1", frame_index=1),
    ]
    result = propagate_roster_position_by_track(annotations)
    assert result[1].position is None


def test_propagate_roster_position_raises_on_conflicting_reviewed_labels():
    annotations = [
        _box_ann(track_id="t1", frame_index=0, position=RosterPosition.S, reviewed=True),
        _box_ann(track_id="t1", frame_index=5, position=RosterPosition.MB, reviewed=True),
    ]
    with pytest.raises(ConflictingTrackPositionError, match="conflicting reviewed positions"):
        propagate_roster_position_by_track(annotations)


def test_propagate_roster_position_is_scoped_per_video():
    """The same track_id string in two different videos must never cross-
    contaminate -- track ids are only unique within one clip/video."""
    annotations = [
        _box_ann(
            track_id="t1",
            frame_index=0,
            position=RosterPosition.S,
            reviewed=True,
            video_id="video-a",
        ),
        _box_ann(track_id="t1", frame_index=0, video_id="video-b"),
    ]
    result = propagate_roster_position_by_track(annotations)
    video_b_ann = next(ann for ann in result if ann.provenance.video_id == "video-b")
    assert video_b_ann.position is None
