import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from volley_domain.analysis import (
    AnalysisCalibration,
    AnalysisCapability,
    AnalysisModelRunRef,
    AnalysisProvenance,
    AnalyzedContact,
    BallTrajectorySample,
    PlayerStateSample,
    RallyAnalysisBundle,
    SourceFrameRef,
)
from volley_domain.analysis_persistence import canonical_bundle_sha256, persist_rally_analysis
from volley_domain.annotation import BoundingBox, PixelPoint, ScalarMeasurement
from volley_domain.base import Base
from volley_domain.models import Match, MatchStatus
from volley_domain.ontology import (
    ActionType,
    BallProvenance,
    ModelRun,
    ModelRunStage,
    PipelineRun,
    PipelineRunStatus,
    Rally,
    RallyAnalysisResult,
    Team,
    Video,
    VideoStatus,
)
from volley_domain.ontology import MatchSet as MatchSetRow


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _frame(index: int) -> SourceFrameRef:
    return SourceFrameRef(
        source_pts=index * 256,
        source_time_base="1/12800",
        source_timestamp_seconds=index / 50,
        normalized_timestamp_seconds=index / 50,
        proxy_frame_index=index,
    )


def _bundle() -> RallyAnalysisBundle:
    frame = _frame(10)
    return RallyAnalysisBundle(
        provenance=AnalysisProvenance(
            organization_id="org-1",
            video_id="video-1",
            video_hash="a" * 64,
            pipeline_run_id="pipeline-1",
            pipeline_version="professional-v1",
            config_sha256="b" * 64,
            code_commit="abcdef1",
            model_runs=[
                AnalysisModelRunRef(
                    stage="ball_trajectory",
                    model_run_id="model-1",
                    model_version="ball-v1",
                    weights_sha256="c" * 64,
                    dataset_version="golden-v1",
                )
            ],
        ),
        rally_id="rally-1",
        set_index=1,
        rally_index_in_set=1,
        start_frame=frame,
        end_frame=_frame(20),
        calibration=AnalysisCalibration(
            calibration_id="calibration-1",
            frame_width_px=1280,
            frame_height_px=720,
            confidence=0.9,
            reprojection_error_px=1.2,
            supports_court_plane=True,
            supports_metric_3d=False,
            camera_count=1,
        ),
        ball_trajectory=[
            BallTrajectorySample(
                frame=frame,
                center_pixel=PixelPoint(x=600, y=200),
                provenance=BallProvenance.OBSERVED,
                confidence=0.9,
            )
        ],
        player_states=[
            PlayerStateSample(
                frame=frame,
                track_id="server",
                team="home",
                bbox=BoundingBox(x=0.1, y=0.1, width=0.2, height=0.5),
                confidence=0.9,
            )
        ],
        contacts=[
            AnalyzedContact(
                contact_id="contact-1",
                contact_index=1,
                frame=frame,
                actor_track_id="server",
                team="home",
                action_type=ActionType.SERVE,
                contact_surface="right_hand",
                ball_center_pixel=PixelPoint(x=600, y=200),
                contact_height=ScalarMeasurement(
                    unit="m",
                    measurement_mode="monocular_physics",
                    confidence=0,
                    status="abstained",
                    abstention_reason="single camera has no validated metric depth",
                ),
                confidence=0.8,
            )
        ],
        capabilities={
            "ball_2d": AnalysisCapability(status="available"),
            "metric_3d_reference": AnalysisCapability(
                status="unavailable", reason="only one synchronized camera is available"
            ),
        },
    )


def _seed_graph(db: Session, *, pipeline_status=PipelineRunStatus.COMPLETED) -> None:
    match = Match(
        id="match-1",
        organization_id="org-1",
        home_team="Alpha VC",
        away_team="Beta VC",
        status=MatchStatus.PROCESSING,
        created_by_user_id="user-1",
    )
    team = Team(id="team-1", organization_id="org-1", name="Alpha VC")
    match_set = MatchSetRow(id="set-1", match_id=match.id, index=0)
    rally = Rally(
        id="rally-1",
        set_id=match_set.id,
        index_in_set=0,
        serving_team_id=team.id,
        video_t_start=0.2,
        video_t_end=0.4,
    )
    video = Video(
        id="video-1",
        organization_id="org-1",
        match_id=match.id,
        filename="match.mp4",
        video_hash="a" * 64,
        uploaded_by_user_id="user-1",
        status=VideoStatus.READY,
    )
    pipeline = PipelineRun(
        id="pipeline-1",
        video_id=video.id,
        pipeline_version="professional-v1",
        config_hash="b" * 64,
        code_commit="abcdef1",
        status=pipeline_status,
    )
    model = ModelRun(
        id="model-1",
        pipeline_run_id=pipeline.id,
        stage=ModelRunStage.BALL_TRAJECTORY,
        model_version="ball-v1",
        weights_hash="c" * 64,
        dataset_version="golden-v1",
    )
    db.add_all([match, team, match_set, rally, video, pipeline, model])
    db.flush()


def test_persist_analysis_is_hashed_and_idempotent(db):
    _seed_graph(db)
    bundle = _bundle()

    first = persist_rally_analysis(db, match_id="match-1", bundle=bundle)
    second = persist_rally_analysis(db, match_id="match-1", bundle=bundle)

    assert first.id == second.id
    assert first.content_sha256 == canonical_bundle_sha256(bundle)
    assert first.bundle_data["schema_version"] == "rally-analysis-v1"
    assert len(db.execute(select(RallyAnalysisResult)).scalars().all()) == 1


def test_persist_analysis_rejects_incomplete_pipeline(db):
    _seed_graph(db, pipeline_status=PipelineRunStatus.RUNNING)

    with pytest.raises(ValueError, match="only completed pipeline"):
        persist_rally_analysis(db, match_id="match-1", bundle=_bundle())


def test_persist_analysis_rejects_cross_tenant_bundle(db):
    _seed_graph(db)
    payload = _bundle().model_dump()
    payload["provenance"]["organization_id"] = "org-2"

    with pytest.raises(ValueError, match="does not own"):
        persist_rally_analysis(
            db, match_id="match-1", bundle=RallyAnalysisBundle.model_validate(payload)
        )


def test_persist_analysis_never_rewrites_same_version_identity(db):
    _seed_graph(db)
    bundle = _bundle()
    persist_rally_analysis(db, match_id="match-1", bundle=bundle)
    changed = bundle.model_copy(update={"warnings": ["manual review requested"]})

    with pytest.raises(ValueError, match="different content"):
        persist_rally_analysis(db, match_id="match-1", bundle=changed)
