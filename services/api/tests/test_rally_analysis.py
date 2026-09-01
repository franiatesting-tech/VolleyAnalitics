import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from volley_domain.analysis import (
    AnalysisCalibration,
    AnalysisCapability,
    AnalysisModelRunRef,
    AnalysisProvenance,
    RallyAnalysisBundle,
    SourceFrameRef,
)
from volley_domain.analysis_persistence import canonical_bundle_sha256
from volley_domain.ontology import MatchSet as MatchSetRow
from volley_domain.ontology import (
    PipelineRun,
    PipelineRunStatus,
    Rally,
    RallyAnalysisResult,
    Team,
    Video,
    VideoStatus,
)


def _frame(index: int) -> SourceFrameRef:
    return SourceFrameRef(
        source_pts=index * 256,
        source_time_base="1/12800",
        source_timestamp_seconds=index / 50,
        normalized_timestamp_seconds=index / 50,
        proxy_frame_index=index,
    )


def _bundle(*, rally_id: str, video_id: str, pipeline_id: str) -> RallyAnalysisBundle:
    return RallyAnalysisBundle(
        provenance=AnalysisProvenance(
            organization_id="org-1",
            video_id=video_id,
            video_hash="a" * 64,
            pipeline_run_id=pipeline_id,
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
        rally_id=rally_id,
        set_index=1,
        rally_index_in_set=1,
        start_frame=_frame(10),
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
        ball_trajectory=[],
        player_states=[],
        contacts=[],
        capabilities={
            "ball_2d": AnalysisCapability(
                status="unavailable", reason="no reviewed detections for this fixture"
            ),
            "metric_3d_reference": AnalysisCapability(
                status="unavailable", reason="only one synchronized camera is available"
            ),
        },
    )


async def _seed_analysis(db_engine, *, match_id: str, status: PipelineRunStatus) -> str:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as db:
        team = Team(organization_id="org-1", name="Alpha VC")
        db.add(team)
        await db.flush()
        match_set = MatchSetRow(match_id=match_id, index=0)
        db.add(match_set)
        await db.flush()
        rally = Rally(
            set_id=match_set.id,
            index_in_set=0,
            serving_team_id=team.id,
            video_t_start=0.2,
            video_t_end=0.4,
        )
        video = Video(
            organization_id="org-1",
            match_id=match_id,
            filename="match.mp4",
            video_hash="a" * 64,
            uploaded_by_user_id="user-1",
            status=VideoStatus.READY,
        )
        db.add_all([rally, video])
        await db.flush()
        pipeline = PipelineRun(
            video_id=video.id,
            pipeline_version="professional-v1",
            config_hash="b" * 64,
            code_commit="abcdef1",
            status=status,
        )
        db.add(pipeline)
        await db.flush()
        bundle = _bundle(rally_id=rally.id, video_id=video.id, pipeline_id=pipeline.id)
        db.add(
            RallyAnalysisResult(
                organization_id="org-1",
                match_id=match_id,
                rally_id=rally.id,
                video_id=video.id,
                pipeline_run_id=pipeline.id,
                schema_version=bundle.schema_version,
                content_sha256=canonical_bundle_sha256(bundle),
                bundle_data=bundle.model_dump(mode="json"),
            )
        )
        await db.commit()
        return rally.id


@pytest.mark.asyncio
async def test_rally_analysis_returns_completed_versioned_bundle_and_is_org_scoped(
    client, db_engine, override_principal, other_org_principal
):
    created = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    rally_id = await _seed_analysis(
        db_engine, match_id=created.json()["id"], status=PipelineRunStatus.COMPLETED
    )

    response = await client.get(f"/api/v1/rallies/{rally_id}/analysis")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "rally-analysis-v1"
    assert payload["bundle"]["rally_id"] == rally_id
    assert payload["bundle"]["capabilities"]["metric_3d_reference"]["status"] == "unavailable"
    assert len(payload["content_sha256"]) == 64

    override_principal["value"] = other_org_principal
    assert (await client.get(f"/api/v1/rallies/{rally_id}/analysis")).status_code == 404


@pytest.mark.asyncio
async def test_rally_analysis_does_not_publish_running_pipeline(client, db_engine):
    created = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    rally_id = await _seed_analysis(
        db_engine, match_id=created.json()["id"], status=PipelineRunStatus.RUNNING
    )

    response = await client.get(f"/api/v1/rallies/{rally_id}/analysis")

    assert response.status_code == 404
    assert "No completed professional analysis" in response.json()["error"]["message"]
