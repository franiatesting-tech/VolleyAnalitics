"""Typed, animation-ready output contract for one analyzed volleyball rally."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from volley_domain.annotation import (
    VOLLEY_SKELETON_KEYPOINTS,
    BoundingBox,
    ContactSurface,
    PixelPoint,
    ScalarMeasurement,
    SpatialEstimate3D,
    TeamSide,
    Vector3D,
)
from volley_domain.ontology import ActionType, BallProvenance


class SourceFrameRef(BaseModel):
    """Exact source/proxy mapping; never identifies a frame by index alone."""

    source_pts: int
    source_time_base: str = Field(pattern=r"^[1-9][0-9]*/[1-9][0-9]*$")
    source_timestamp_seconds: float = Field(ge=0)
    normalized_timestamp_seconds: float = Field(ge=0)
    proxy_frame_index: int = Field(ge=0)


class AnalysisModelRunRef(BaseModel):
    stage: str = Field(min_length=1)
    model_run_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    weights_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    dataset_version: str = Field(min_length=1)


class AnalysisProvenance(BaseModel):
    organization_id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    video_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    pipeline_run_id: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    config_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    code_commit: str = Field(pattern=r"^[a-fA-F0-9]{7,64}$")
    model_runs: list[AnalysisModelRunRef] = Field(min_length=1)

    @model_validator(mode="after")
    def _stages_are_unique(self) -> AnalysisProvenance:
        stages = [model.stage for model in self.model_runs]
        if len(stages) != len(set(stages)):
            raise ValueError("analysis model stages must be unique")
        return self


class AnalysisCalibration(BaseModel):
    calibration_id: str = Field(min_length=1)
    frame_width_px: int = Field(ge=1)
    frame_height_px: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)
    reprojection_error_px: float = Field(ge=0)
    supports_court_plane: bool
    supports_metric_3d: bool
    camera_count: int = Field(ge=1)

    @model_validator(mode="after")
    def _metric_3d_needs_multiple_cameras(self) -> AnalysisCalibration:
        if self.supports_metric_3d and self.camera_count < 2:
            raise ValueError("reference metric 3D requires at least two calibrated cameras")
        return self


class BallTrajectorySample(BaseModel):
    frame: SourceFrameRef
    center_pixel: PixelPoint | None = None
    world_3d: SpatialEstimate3D | None = None
    velocity_mps: Vector3D | None = None
    provenance: BallProvenance
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _observed_sample_has_a_location(self) -> BallTrajectorySample:
        if self.provenance == BallProvenance.OBSERVED and self.center_pixel is None:
            raise ValueError("observed ball samples require a 2D pixel centre")
        if self.velocity_mps is not None and self.world_3d is None:
            raise ValueError("metric ball velocity requires a 3D position estimate")
        return self


class AnalysisPoseKeypoint(BaseModel):
    name: str
    pixel: PixelPoint | None = None
    world_3d: SpatialEstimate3D | None = None
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _known_and_located(self) -> AnalysisPoseKeypoint:
        if self.name not in VOLLEY_SKELETON_KEYPOINTS:
            raise ValueError(f"unknown volleyball keypoint: {self.name}")
        if self.pixel is None and self.world_3d is None:
            raise ValueError("pose keypoint requires a 2D or 3D location")
        return self


class PlayerStateSample(BaseModel):
    frame: SourceFrameRef
    track_id: str = Field(min_length=1)
    roster_id: str | None = None
    team: TeamSide
    bbox: BoundingBox
    court_anchor: SpatialEstimate3D | None = None
    pose: list[AnalysisPoseKeypoint] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _pose_names_are_unique(self) -> PlayerStateSample:
        names = [keypoint.name for keypoint in self.pose]
        if len(names) != len(set(names)):
            raise ValueError("player pose keypoint names must be unique")
        return self


class AnalyzedContact(BaseModel):
    contact_id: str = Field(min_length=1)
    contact_index: int = Field(ge=1)
    frame: SourceFrameRef
    actor_track_id: str = Field(min_length=1)
    team: TeamSide
    action_type: ActionType
    contact_surface: ContactSurface
    ball_center_pixel: PixelPoint
    ball_world_3d: SpatialEstimate3D | None = None
    contact_height: ScalarMeasurement
    incoming_velocity_mps: Vector3D | None = None
    outgoing_velocity_mps: Vector3D | None = None
    target_court_point: SpatialEstimate3D | None = None
    confidence: float = Field(ge=0, le=1)


class AnalysisCapability(BaseModel):
    status: Literal["available", "estimated", "abstained", "unavailable"]
    reason: str | None = None

    @model_validator(mode="after")
    def _non_available_has_reason(self) -> AnalysisCapability:
        if self.status != "available" and not self.reason:
            raise ValueError("estimated/abstained/unavailable capabilities require a reason")
        return self


class RallyAnalysisBundle(BaseModel):
    schema_version: Literal["rally-analysis-v1"] = "rally-analysis-v1"
    provenance: AnalysisProvenance
    rally_id: str = Field(min_length=1)
    set_index: int = Field(ge=1, le=5)
    rally_index_in_set: int = Field(ge=1)
    start_frame: SourceFrameRef
    end_frame: SourceFrameRef
    calibration: AnalysisCalibration
    ball_trajectory: list[BallTrajectorySample]
    player_states: list[PlayerStateSample]
    contacts: list[AnalyzedContact]
    biomechanical_metrics: list[ScalarMeasurement] = Field(default_factory=list)
    capabilities: dict[str, AnalysisCapability]
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _signals_are_temporally_and_semantically_linked(self) -> RallyAnalysisBundle:
        start = self.start_frame.normalized_timestamp_seconds
        end = self.end_frame.normalized_timestamp_seconds
        if end < start:
            raise ValueError("rally end precedes rally start")

        def timestamp(frame: SourceFrameRef) -> float:
            return frame.normalized_timestamp_seconds

        ball_times = [timestamp(sample.frame) for sample in self.ball_trajectory]
        if ball_times != sorted(ball_times):
            raise ValueError("ball trajectory must be time ordered")
        if any(not start <= value <= end for value in ball_times):
            raise ValueError("ball trajectory contains samples outside rally boundaries")

        contacts = sorted(self.contacts, key=lambda item: item.contact_index)
        if contacts != self.contacts:
            raise ValueError("contacts must be stored in contact order")
        if [item.contact_index for item in contacts] != list(range(1, len(contacts) + 1)):
            raise ValueError("contact indexes must be contiguous and start at 1")

        ball_frames = {sample.frame.proxy_frame_index for sample in self.ball_trajectory}
        player_frames = {
            (sample.frame.proxy_frame_index, sample.track_id) for sample in self.player_states
        }
        for contact in contacts:
            frame_index = contact.frame.proxy_frame_index
            if frame_index not in ball_frames:
                raise ValueError(f"contact {contact.contact_id} lacks exact-frame ball state")
            if (frame_index, contact.actor_track_id) not in player_frames:
                raise ValueError(f"contact {contact.contact_id} lacks exact-frame actor state")

        metric_3d = self.capabilities.get("metric_3d_reference")
        if metric_3d and metric_3d.status == "available":
            if not self.calibration.supports_metric_3d:
                raise ValueError("metric 3D capability contradicts the calibration")
            world_samples = [
                sample.world_3d for sample in self.ball_trajectory if sample.world_3d is not None
            ]
            if not world_samples or any(
                sample.measurement_mode != "triangulated" for sample in world_samples
            ):
                raise ValueError("metric 3D reference requires triangulated ball samples")
        return self
