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
from volley_domain.annotation import BoundingBox, PixelPoint, ScalarMeasurement
from volley_domain.ontology import ActionType, BallProvenance


def _frame(index: int) -> SourceFrameRef:
    return SourceFrameRef(
        source_pts=index * 256,
        source_time_base="1/12800",
        source_timestamp_seconds=index / 50,
        normalized_timestamp_seconds=index / 50,
        proxy_frame_index=index,
    )


def _provenance() -> AnalysisProvenance:
    return AnalysisProvenance(
        organization_id="org-1",
        video_id="video-1",
        video_hash="a" * 64,
        pipeline_run_id="pipeline-1",
        pipeline_version="professional-v1",
        config_sha256="b" * 64,
        code_commit="abcdef1",
        model_runs=[
            AnalysisModelRunRef(
                stage="ball_tracking",
                model_run_id="model-1",
                model_version="ball-v1",
                weights_sha256="c" * 64,
                dataset_version="golden-v1",
            )
        ],
    )


def _bundle() -> RallyAnalysisBundle:
    ball = BallTrajectorySample(
        frame=_frame(10),
        center_pixel=PixelPoint(x=600, y=200),
        provenance=BallProvenance.OBSERVED,
        confidence=0.9,
    )
    player = PlayerStateSample(
        frame=_frame(10),
        track_id="server",
        team="home",
        bbox=BoundingBox(x=0.1, y=0.1, width=0.2, height=0.5),
        confidence=0.9,
    )
    contact = AnalyzedContact(
        contact_id="contact-1",
        contact_index=1,
        frame=_frame(10),
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
    return RallyAnalysisBundle(
        provenance=_provenance(),
        rally_id="rally-1",
        set_index=1,
        rally_index_in_set=1,
        start_frame=_frame(10),
        end_frame=_frame(20),
        calibration=AnalysisCalibration(
            calibration_id="calibration-1",
            frame_width_px=1280,
            frame_height_px=720,
            confidence=0.9,
            reprojection_error_px=1.5,
            supports_court_plane=True,
            supports_metric_3d=False,
            camera_count=1,
        ),
        ball_trajectory=[ball],
        player_states=[player],
        contacts=[contact],
        capabilities={
            "ball_2d": AnalysisCapability(status="available"),
            "metric_3d_reference": AnalysisCapability(
                status="unavailable",
                reason="only one synchronized camera is available",
            ),
        },
    )


def test_monocular_bundle_is_animation_ready_and_abstains_from_metric_height():
    bundle = _bundle()
    assert bundle.ball_trajectory[0].frame.source_pts == 2560
    assert bundle.contacts[0].contact_height.status == "abstained"
    assert bundle.capabilities["metric_3d_reference"].status == "unavailable"


def test_contact_requires_exact_frame_actor_state():
    payload = _bundle().model_dump()
    payload["player_states"] = []
    try:
        RallyAnalysisBundle.model_validate(payload)
    except ValueError as exc:
        assert "lacks exact-frame actor state" in str(exc)
    else:
        raise AssertionError("bundle accepted an unlinked contact actor")


def test_observed_ball_requires_pixel_location():
    payload = _bundle().ball_trajectory[0].model_dump()
    payload["center_pixel"] = None
    try:
        BallTrajectorySample.model_validate(payload)
    except ValueError as exc:
        assert "require a 2D pixel centre" in str(exc)
    else:
        raise AssertionError("observed ball accepted without a pixel location")


def test_single_camera_cannot_claim_metric_3d():
    payload = _bundle().model_dump()
    payload["capabilities"]["metric_3d_reference"] = {"status": "available"}
    try:
        RallyAnalysisBundle.model_validate(payload)
    except ValueError as exc:
        assert "contradicts the calibration" in str(exc)
    else:
        raise AssertionError("single-camera bundle claimed metric 3D reference")
