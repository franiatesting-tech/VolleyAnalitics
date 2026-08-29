"""Verifies HumanCorrection/ReviewedLabel are genuinely append-only against
a real (SQLite) database -- not just by code inspection. See
docs/domain/ONTOLOGY.md's "Correction semantics" section.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from volley_domain.base import Base
from volley_domain.corrections import correction_history, record_correction, record_review
from volley_domain.ontology import (
    Action,
    CorrectionTargetType,
    HumanCorrection,
    ModelRun,
    ModelRunStage,
    Phase,
    PhaseType,
    PipelineRun,
    PipelineRunStatus,
    Rally,
    ReviewedLabel,
    ReviewStatus,
    Team,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_action(db: Session) -> Action:
    home = Team(organization_id="org-1", name="Home")
    away = Team(organization_id="org-1", name="Away")
    db.add_all([home, away])
    db.flush()

    rally = Rally(set_id="set-1", index_in_set=0, serving_team_id=home.id)
    db.add(rally)
    db.flush()

    phase = Phase(rally_id=rally.id, index_in_rally=0, phase_type=PhaseType.SERVE)
    db.add(phase)
    db.flush()

    pipeline_run = PipelineRun(
        video_id=None,
        pipeline_version="test-v1",
        config_hash="test-hash",
        status=PipelineRunStatus.COMPLETED,
    )
    db.add(pipeline_run)
    db.flush()

    model_run = ModelRun(
        pipeline_run_id=pipeline_run.id,
        stage=ModelRunStage.SYNTHETIC,
        model_version="test-v1",
    )
    db.add(model_run)
    db.flush()

    action = Action(
        phase_id=phase.id,
        rally_id=rally.id,
        index_in_phase=0,
        action_type="attack",
        actor_team_id=home.id,
        video_t_start=0.0,
        video_t_end=1.0,
        court_x=0.5,
        court_y=0.5,
        confidence=0.9,
        model_run_id=model_run.id,
    )
    db.add(action)
    db.commit()
    return action


def test_record_correction_inserts_append_only_row(db):
    action = _make_action(db)

    correction = record_correction(
        db,
        target_type=CorrectionTargetType.ACTION,
        target_id=action.id,
        field_name="action_type",
        previous_value={"action_type": "attack"},
        corrected_value={"action_type": "tip"},
        corrected_by_user_id="coach-1",
        reason="Video review: soft touch, not a full swing",
    )
    db.commit()

    assert correction.id is not None
    stored = db.get(HumanCorrection, correction.id)
    assert stored.previous_value == {"action_type": "attack"}
    assert stored.corrected_value == {"action_type": "tip"}
    assert stored.reason == "Video review: soft touch, not a full swing"


def test_correction_never_destroys_original_prediction_row(db):
    """The whole point: after applying a correction, the Action's original
    model_run_id/confidence (the prediction's own provenance) must remain
    untouched, and the original value must still be reconstructible from
    the correction log even though the Action's displayed value changed."""
    action = _make_action(db)
    original_confidence = action.confidence

    record_correction(
        db,
        target_type=CorrectionTargetType.ACTION,
        target_id=action.id,
        field_name="action_type",
        previous_value={"action_type": "attack"},
        corrected_value={"action_type": "tip"},
        corrected_by_user_id="coach-1",
    )
    # Caller applies the corrected value for ordinary reads -- a separate,
    # deliberate step (see corrections.py's record_correction docstring).
    action.action_type = "tip"
    db.commit()

    refreshed = db.get(Action, action.id)
    assert refreshed.action_type == "tip"  # ordinary reads see the correction
    assert refreshed.confidence == original_confidence  # provenance untouched

    history = correction_history(db, target_type=CorrectionTargetType.ACTION, target_id=action.id)
    assert len(history) == 1
    assert history[0].previous_value == {"action_type": "attack"}  # original still reconstructible


def test_correction_history_is_append_only_across_multiple_corrections(db):
    """A second correction must add a new row, never overwrite the first."""
    action = _make_action(db)

    record_correction(
        db,
        target_type=CorrectionTargetType.ACTION,
        target_id=action.id,
        field_name="action_type",
        previous_value={"action_type": "attack"},
        corrected_value={"action_type": "tip"},
        corrected_by_user_id="coach-1",
    )
    db.commit()
    record_correction(
        db,
        target_type=CorrectionTargetType.ACTION,
        target_id=action.id,
        field_name="action_type",
        previous_value={"action_type": "tip"},
        corrected_value={"action_type": "attack"},
        corrected_by_user_id="coach-2",
        reason="Second look: it was a full swing after all",
    )
    db.commit()

    history = correction_history(db, target_type=CorrectionTargetType.ACTION, target_id=action.id)
    assert len(history) == 2
    assert history[0].corrected_by_user_id == "coach-1"
    assert history[1].corrected_by_user_id == "coach-2"
    # The very first correction's previous_value is still exactly what the
    # model originally predicted, unaffected by the second correction.
    assert history[0].previous_value == {"action_type": "attack"}


def test_record_review_without_correction_means_confirmed_as_is(db):
    action = _make_action(db)

    review = record_review(
        db,
        target_type=CorrectionTargetType.ACTION,
        target_id=action.id,
        reviewed_by_user_id="coach-1",
        status=ReviewStatus.CONFIRMED,
    )
    db.commit()

    stored = db.get(ReviewedLabel, review.id)
    assert stored.status == ReviewStatus.CONFIRMED
    # No HumanCorrection exists for this target -- confirming isn't correcting.
    assert (
        correction_history(db, target_type=CorrectionTargetType.ACTION, target_id=action.id) == []
    )
