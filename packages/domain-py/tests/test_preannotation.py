from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from volley_domain.annotation import BoundingBox, FrameRef, PixelPoint
from volley_domain.ontology import ActionType
from volley_domain.preannotation import (
    ContactPreannotation,
    PlayerTrackPreannotation,
    PredictionProvenance,
    ReviewAudit,
    assert_review_created_ground_truth,
)


def _provenance() -> PredictionProvenance:
    return PredictionProvenance(
        organization_id="org-1",
        video_id="video-1",
        video_hash="a" * 64,
        pipeline_run_id="pipeline-1",
        model_run_id="model-run-1",
        stage="player_detection",
        model_family="RF-DETR",
        model_version="nano-smoke-v1",
        weights_sha256="b" * 64,
        config_sha256="c" * 64,
        training_dataset_version="pretrained-coco",
        code_commit="abcdef1",
        source_sha256="d" * 64,
        created_at=datetime.now(UTC),
    )


def _track(*, review: ReviewAudit | None = None) -> PlayerTrackPreannotation:
    return PlayerTrackPreannotation(
        candidate_id="candidate-1",
        provenance=_provenance(),
        frame=FrameRef(frame_index=25, timestamp_seconds=0.5),
        track_id="track-7",
        bbox=BoundingBox(x=0.1, y=0.1, width=0.2, height=0.5),
        person_role="on_court_player",
        role_confidence=0.99,
        confidence=0.82,
        review=review or ReviewAudit(),
    )


def test_unreviewed_prediction_cannot_impersonate_ground_truth():
    with pytest.raises(ValueError, match="separately reviewed ground truth"):
        assert_review_created_ground_truth(_track())


def test_accepted_prediction_requires_separate_ground_truth_record():
    with pytest.raises(ValidationError, match="separate ground_truth_id"):
        ReviewAudit(
            status="accepted",
            reviewer_id="reviewer-1",
            reviewed_at=datetime.now(UTC),
        )


def test_accepted_prediction_links_to_reviewed_ground_truth():
    item = _track(
        review=ReviewAudit(
            status="corrected",
            reviewer_id="reviewer-1",
            reviewed_at=datetime.now(UTC),
            ground_truth_id="cvat-ground-truth-9",
        )
    )
    assert assert_review_created_ground_truth(item) == "cvat-ground-truth-9"


def test_contact_preannotation_rejects_transition_phase():
    with pytest.raises(ValidationError, match="transition cannot be proposed"):
        ContactPreannotation(
            candidate_id="contact-1",
            provenance=_provenance(),
            frame=FrameRef(frame_index=25, timestamp_seconds=0.5),
            actor_track_id="track-7",
            action_type=ActionType.TRANSITION,
            ball_center_pixel=PixelPoint(x=700, y=300),
            confidence=0.7,
            actor_confidence=0.8,
            action_confidence=0.6,
            temporal_uncertainty_frames=2,
        )
