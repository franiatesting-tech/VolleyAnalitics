"""Verifies the CameraSegment/CourtCalibration/BlockAttempt entities added
in response to an external annotation-spec review -- see TECH_DEBT.md and
PROFESSIONAL_ANNOTATION_PROTOCOL.md for why these exist -- and the
follow-up fixes from an independent architecture review of that same
addition (B1-B5 in TECH_DEBT.md's entry): CourtCalibration realigned with
volley_domain.annotation.CameraCalibrationAnnotation, BlockAttempt's
provenance made required like Action's, CorrectionTargetType extended."""

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from volley_domain.base import Base
from volley_domain.models import Match, MatchStatus
from volley_domain.ontology import (
    Action,
    ActionType,
    BlockAttempt,
    BlockMode,
    BlockRole,
    CameraSegment,
    CorrectionTargetType,
    CourtCalibration,
    HomographyMethod,
    ModelRun,
    ModelRunStage,
    Outcome,
    OutcomeResult,
    Phase,
    PhaseType,
    PipelineRun,
    PipelineRunStatus,
    Rally,
    ShotType,
    TacticalUsability,
    Team,
    Video,
    VideoStatus,
)
from volley_domain.ontology import MatchSet as MatchSetRow


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_video(db: Session, organization_id: str = "org-1") -> Video:
    video = Video(
        organization_id=organization_id,
        filename="clip.mp4",
        uploaded_by_user_id="user-1",
        status=VideoStatus.READY,
    )
    db.add(video)
    db.commit()
    return video


def _make_rally(db: Session) -> tuple[Rally, Team, Team]:
    match = Match(
        organization_id="org-1",
        home_team="Alpha VC",
        away_team="Beta VC",
        status=MatchStatus.PROCESSING,
        created_by_user_id="user-1",
    )
    db.add(match)
    db.commit()

    home = Team(organization_id="org-1", name="Alpha VC")
    away = Team(organization_id="org-1", name="Beta VC")
    db.add_all([home, away])
    db.commit()

    match_set = MatchSetRow(match_id=match.id, index=0)
    db.add(match_set)
    db.commit()

    rally = Rally(set_id=match_set.id, index_in_set=0, serving_team_id=home.id)
    db.add(rally)
    db.commit()
    return rally, home, away


def _make_model_run(db: Session) -> ModelRun:
    pipeline_run = PipelineRun(
        video_id=None,
        pipeline_version="test-v1",
        config_hash="a" * 8,
        status=PipelineRunStatus.COMPLETED,
    )
    db.add(pipeline_run)
    db.commit()
    model_run = ModelRun(
        pipeline_run_id=pipeline_run.id, stage=ModelRunStage.SYNTHETIC, model_version="test"
    )
    db.add(model_run)
    db.commit()
    return model_run


def test_camera_segment_index_is_unique_per_video(db):
    video = _make_video(db)
    db.add(
        CameraSegment(
            video_id=video.id,
            index_in_video=0,
            video_t_start=0.0,
            shot_type=ShotType.MAIN_WIDE,
            tactical_usable=TacticalUsability.USABLE,
        )
    )
    db.commit()
    db.add(
        CameraSegment(
            video_id=video.id,
            index_in_video=0,  # duplicate index for the same video
            video_t_start=30.0,
            shot_type=ShotType.REPLAY,
            tactical_usable=TacticalUsability.NOT_USABLE,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_replay_segment_is_marked_not_tactically_usable(db):
    """Direct regression for the exact gap this entity closes: a replay or
    close-up must never silently mix into real-match statistics."""
    video = _make_video(db)
    replay = CameraSegment(
        video_id=video.id,
        index_in_video=1,
        video_t_start=45.0,
        video_t_end=52.0,
        shot_type=ShotType.REPLAY,
        tactical_usable=TacticalUsability.NOT_USABLE,
    )
    db.add(replay)
    db.commit()

    fetched = db.get(CameraSegment, replay.id)
    assert fetched.tactical_usable == TacticalUsability.NOT_USABLE
    assert fetched.shot_type == ShotType.REPLAY


def test_court_calibration_persists_homography_and_keypoints_as_json(db):
    """Keypoint field names/polarity must match
    volley_domain.annotation.CourtKeypointAnnotation exactly
    (keypoint_name/x_pixel/y_pixel/visible) -- an earlier draft used
    kp_name/pixel_x/pixel_y/occluded, with occluded/visible being
    literally inverted polarity of the same fact."""
    video = _make_video(db)
    segment = CameraSegment(
        video_id=video.id,
        index_in_video=0,
        video_t_start=0.0,
        shot_type=ShotType.MAIN_WIDE,
        tactical_usable=TacticalUsability.USABLE,
    )
    db.add(segment)
    db.commit()

    identity_matrix = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    keypoints = [
        {
            "keypoint_name": "sideline_near_left",
            "x_pixel": 100.0,
            "y_pixel": 600.0,
            "visible": True,
        },
        {
            "keypoint_name": "sideline_far_right",
            "x_pixel": 900.0,
            "y_pixel": 50.0,
            "visible": False,
        },
    ]
    calibration = CourtCalibration(
        camera_segment_id=segment.id,
        method=HomographyMethod.AUTOMATIC,
        image_width=1280,
        image_height=720,
        homography_matrix=identity_matrix,
        keypoints=keypoints,
        reprojection_error_px=1.4,
        confidence=0.92,
    )
    db.add(calibration)
    db.commit()

    fetched = db.get(CourtCalibration, calibration.id)
    assert fetched.homography_matrix == identity_matrix
    assert fetched.keypoints == keypoints
    assert fetched.method == HomographyMethod.AUTOMATIC
    assert fetched.image_width == 1280
    assert fetched.image_height == 720
    assert fetched.supports_metric_3d is False  # default, no camera model supplied


def test_court_calibration_supports_phase_b_metric_3d_fields(db):
    """The optional camera_matrix/rotation/translation fields exist
    specifically so a Phase B multi-camera calibration has somewhere to
    record them, mirroring CameraCalibrationAnnotation's own fields."""
    video = _make_video(db)
    segment = CameraSegment(
        video_id=video.id,
        index_in_video=0,
        video_t_start=0.0,
        shot_type=ShotType.MAIN_WIDE,
        tactical_usable=TacticalUsability.USABLE,
    )
    db.add(segment)
    db.commit()

    calibration = CourtCalibration(
        camera_segment_id=segment.id,
        method=HomographyMethod.HYBRID,
        image_width=1920,
        image_height=1080,
        homography_matrix=[1.0] * 9,
        camera_matrix=[1000.0, 0.0, 960.0, 0.0, 1000.0, 540.0, 0.0, 0.0, 1.0],
        rotation_world_to_camera=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        translation_world_to_camera_m=[0.0, -5.0, 3.0],
        supports_metric_3d=True,
        created_by_user_id="user-1",
    )
    db.add(calibration)
    db.commit()

    fetched = db.get(CourtCalibration, calibration.id)
    assert fetched.supports_metric_3d is True
    assert fetched.camera_matrix is not None
    assert fetched.created_by_user_id == "user-1"
    assert fetched.method == HomographyMethod.HYBRID


def test_a_camera_segment_can_accumulate_a_superseding_calibration(db):
    """A manual recalibration must not delete the earlier automatic one --
    both remain for audit. Superseded rows are marked via superseded_at,
    not sorted by created_at (two calibrations in one transaction can
    share an identical Postgres now())."""
    video = _make_video(db)
    segment = CameraSegment(
        video_id=video.id,
        index_in_video=0,
        video_t_start=0.0,
        shot_type=ShotType.MAIN_WIDE,
        tactical_usable=TacticalUsability.USABLE,
    )
    db.add(segment)
    db.commit()

    auto = CourtCalibration(
        camera_segment_id=segment.id,
        method=HomographyMethod.AUTOMATIC,
        image_width=1280,
        image_height=720,
        homography_matrix=[1.0] * 9,
        reprojection_error_px=4.2,
    )
    db.add(auto)
    db.commit()

    manual = CourtCalibration(
        camera_segment_id=segment.id,
        method=HomographyMethod.MANUAL,
        image_width=1280,
        image_height=720,
        homography_matrix=[1.0] * 9,
        reprojection_error_px=0.8,
        created_by_user_id="user-1",
    )
    db.add(manual)
    db.commit()

    auto.superseded_at = manual.created_at
    db.commit()

    calibrations = (
        db.execute(select(CourtCalibration).where(CourtCalibration.camera_segment_id == segment.id))
        .scalars()
        .all()
    )
    assert len(calibrations) == 2
    current = [c for c in calibrations if c.superseded_at is None]
    assert len(current) == 1
    assert current[0].id == manual.id


def test_block_attempt_without_a_touch_has_no_action_link(db):
    """The exact case this entity exists for: a blocker who jumped but
    never touched the ball -- previously unrepresentable at all."""
    rally, home, away = _make_rally(db)
    model_run = _make_model_run(db)
    attempt = BlockAttempt(
        rally_id=rally.id,
        actor_team_id=away.id,
        video_t=12.4,
        court_x=0.5,
        court_y=0.1,
        block_mode=BlockMode.READ,
        block_role=BlockRole.MIDDLE,
        jumped=True,
        model_run_id=model_run.id,
        confidence=0.8,
    )
    db.add(attempt)
    db.commit()

    fetched = db.get(BlockAttempt, attempt.id)
    assert fetched.action_id is None
    assert fetched.jumped is True
    assert fetched.block_mode == BlockMode.READ


def test_block_attempt_that_touched_the_ball_links_to_its_action(db):
    """When the blocker DID touch the ball, both a BlockAttempt (tactical
    participation) and an Action(action_type=BLOCK) (the contact itself)
    exist for the same event, linked via action_id."""
    rally, home, away = _make_rally(db)
    model_run = _make_model_run(db)

    phase = Phase(rally_id=rally.id, index_in_rally=0, phase_type=PhaseType.TRANSITION)
    db.add(phase)
    db.commit()

    action = Action(
        phase_id=phase.id,
        rally_id=rally.id,
        index_in_phase=0,
        action_type=ActionType.BLOCK,
        actor_team_id=away.id,
        video_t_start=12.4,
        video_t_end=12.6,
        court_x=0.5,
        court_y=0.1,
        confidence=0.9,
        model_run_id=model_run.id,
    )
    db.add(action)
    db.commit()
    db.add(Outcome(action_id=action.id, result=OutcomeResult.POINT))
    db.commit()

    attempt = BlockAttempt(
        rally_id=rally.id,
        actor_team_id=away.id,
        video_t=12.4,
        court_x=0.5,
        court_y=0.1,
        block_mode=BlockMode.COMMIT,
        block_role=BlockRole.SOLO,
        jumped=True,
        action_id=action.id,
        model_run_id=model_run.id,
        confidence=0.9,
    )
    db.add(attempt)
    db.commit()

    fetched = db.get(BlockAttempt, attempt.id)
    assert fetched.action_id == action.id
    linked_action = db.get(Action, fetched.action_id)
    assert linked_action.action_type == ActionType.BLOCK


def test_block_attempt_defaults_to_unknown_mode_and_role(db):
    rally, home, away = _make_rally(db)
    model_run = _make_model_run(db)
    attempt = BlockAttempt(
        rally_id=rally.id,
        actor_team_id=away.id,
        video_t=1.0,
        court_x=0.5,
        court_y=0.1,
        model_run_id=model_run.id,
        confidence=0.7,
    )
    db.add(attempt)
    db.commit()

    fetched = db.get(BlockAttempt, attempt.id)
    assert fetched.block_mode == BlockMode.UNKNOWN
    assert fetched.block_role == BlockRole.UNKNOWN


def test_block_attempt_requires_a_model_run(db):
    """model_run_id is NOT NULL -- same reasoning as Action's own field.
    Without it there is no way to resolve which video a bare video_t
    float even refers to (Rally -> MatchSet -> Match -> Video is nullable
    and one-to-many)."""
    rally, home, away = _make_rally(db)
    with pytest.raises((IntegrityError, TypeError)):
        db.add(
            BlockAttempt(
                rally_id=rally.id,
                actor_team_id=away.id,
                video_t=1.0,
                court_x=0.5,
                court_y=0.1,
                confidence=0.5,
            )
        )
        db.commit()


def test_deleting_a_model_run_cascades_to_its_block_attempts_leaving_no_orphans(db):
    """Regression for the exact bug the nullable/SET-NULL model_run_id
    used to allow: delete a ModelRun and its Actions CASCADE away, but a
    BlockAttempt for the same event would previously survive with both
    FKs nulled -- a ghost row that could double-count in block
    aggregates. Requires SQLite's FK pragma enabled (see the db fixture)
    since this project's other tests don't otherwise exercise ON DELETE
    semantics."""
    rally, home, away = _make_rally(db)
    model_run = _make_model_run(db)
    attempt = BlockAttempt(
        rally_id=rally.id,
        actor_team_id=away.id,
        video_t=1.0,
        court_x=0.5,
        court_y=0.1,
        model_run_id=model_run.id,
        confidence=0.6,
    )
    db.add(attempt)
    db.commit()
    attempt_id = attempt.id

    db.delete(model_run)
    db.commit()

    assert db.get(BlockAttempt, attempt_id) is None


def test_correction_target_type_covers_the_new_entities():
    """B5: block_mode is the most subjective field this project records
    ("do not guess"), and a manual recalibration superseding an automatic
    one is a textbook human correction -- both need a legal correction
    target."""
    assert CorrectionTargetType.BLOCK_ATTEMPT == "block_attempt"
    assert CorrectionTargetType.COURT_CALIBRATION == "court_calibration"
    assert CorrectionTargetType.CAMERA_SEGMENT == "camera_segment"
