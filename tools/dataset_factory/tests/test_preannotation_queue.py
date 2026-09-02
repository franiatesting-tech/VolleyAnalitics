from datetime import UTC, datetime

import pytest
from dataset_factory.preannotation_queue import build_review_queue
from volley_domain.annotation import BoundingBox, FrameRef, PixelPoint
from volley_domain.ontology import ActionType
from volley_domain.preannotation import (
    BallFramePreannotation,
    ContactPreannotation,
    PlayerTrackPreannotation,
    PredictionProvenance,
)


def _provenance() -> PredictionProvenance:
    return PredictionProvenance(
        organization_id="org-1",
        video_id="video-1",
        video_hash="a" * 64,
        pipeline_run_id="pipeline-1",
        model_run_id="model-run-1",
        stage="preannotation",
        model_family="test-model",
        model_version="v1",
        weights_sha256="b" * 64,
        config_sha256="c" * 64,
        training_dataset_version="pretrained",
        code_commit="abcdef1",
        source_sha256="d" * 64,
        created_at=datetime.now(UTC),
    )


def test_contact_is_reviewed_before_ordinary_player_box():
    provenance = _provenance()
    contact = ContactPreannotation(
        candidate_id="contact-1",
        provenance=provenance,
        frame=FrameRef(frame_index=100, timestamp_seconds=2),
        actor_track_id="track-1",
        action_type=ActionType.ATTACK,
        ball_center_pixel=PixelPoint(x=500, y=200),
        confidence=0.9,
        actor_confidence=0.9,
        action_confidence=0.9,
        temporal_uncertainty_frames=0,
    )
    player = PlayerTrackPreannotation(
        candidate_id="player-1",
        provenance=provenance,
        frame=FrameRef(frame_index=50, timestamp_seconds=1),
        track_id="track-1",
        bbox=BoundingBox(x=0.1, y=0.1, width=0.2, height=0.5),
        person_role="on_court_player",
        role_confidence=0.99,
        confidence=0.95,
    )
    queue = build_review_queue([player, contact])
    assert [item.candidate_id for item in queue] == ["contact-1", "player-1"]


def test_ambiguous_ball_visibility_is_prioritized():
    provenance = _provenance()
    ambiguous = BallFramePreannotation(
        candidate_id="ball-ambiguous",
        provenance=provenance,
        frame=FrameRef(frame_index=20, timestamp_seconds=0.4),
        center_pixel=PixelPoint(x=600, y=120),
        visible_probability=0.5,
        confidence=0.7,
    )
    clear = BallFramePreannotation(
        candidate_id="ball-clear",
        provenance=provenance,
        frame=FrameRef(frame_index=21, timestamp_seconds=0.42),
        center_pixel=PixelPoint(x=601, y=121),
        visible_probability=0.99,
        confidence=0.7,
    )
    queue = build_review_queue([clear, ambiguous])
    assert queue[0].candidate_id == "ball-ambiguous"
    assert "ball visibility is ambiguous" in queue[0].reasons


def test_duplicate_candidate_ids_are_rejected():
    provenance = _provenance()
    first = BallFramePreannotation(
        candidate_id="same-id",
        provenance=provenance,
        frame=FrameRef(frame_index=20, timestamp_seconds=0.4),
        visible_probability=0.1,
        confidence=0.9,
    )
    second = first.model_copy(update={"frame": FrameRef(frame_index=21, timestamp_seconds=0.42)})
    with pytest.raises(ValueError, match="candidate_id values must be unique"):
        build_review_queue([first, second])
