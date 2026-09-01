"""Model-assisted annotations that remain strictly separate from ground truth.

Every item in this module is a prediction proposed to an annotator.  A
prediction only becomes ground truth after the annotation tool creates a
separate reviewed ``volley_domain.annotation`` record; changing ``review`` on
one of these objects never makes it eligible for training by itself.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from volley_domain.annotation import (
    VOLLEY_SKELETON_KEYPOINTS,
    BoundingBox,
    ContactSurface,
    FrameRef,
    KeypointVisibility,
    PersonRole,
    PixelPoint,
    TeamSide,
)
from volley_domain.ontology import ActionType

ReviewStatus = Literal["unreviewed", "accepted", "corrected", "rejected"]
TemporalSource = Literal["observed", "interpolated", "predicted"]


class PredictionProvenance(BaseModel):
    """Reproducible identity of the exact model output that proposed a label."""

    organization_id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    video_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    pipeline_run_id: str = Field(min_length=1)
    model_run_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    weights_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    config_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    training_dataset_version: str = Field(min_length=1)
    code_commit: str = Field(pattern=r"^[a-fA-F0-9]{7,64}$")
    source_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    created_at: datetime


class ReviewAudit(BaseModel):
    """Human disposition of a proposal, not a ground-truth record itself."""

    status: ReviewStatus = "unreviewed"
    reviewer_id: str | None = None
    reviewed_at: datetime | None = None
    reason: str | None = None
    ground_truth_id: str | None = None

    @model_validator(mode="after")
    def _review_has_complete_audit_trail(self) -> ReviewAudit:
        if self.status == "unreviewed":
            if any((self.reviewer_id, self.reviewed_at, self.ground_truth_id)):
                raise ValueError("unreviewed proposals cannot carry review completion fields")
            return self
        if not self.reviewer_id or self.reviewed_at is None:
            raise ValueError("reviewed proposals require reviewer_id and reviewed_at")
        if self.status in {"accepted", "corrected"} and not self.ground_truth_id:
            raise ValueError("accepted/corrected proposals require a separate ground_truth_id")
        if self.status == "rejected" and not self.reason:
            raise ValueError("rejected proposals require a reason")
        return self


class PlayerTrackPreannotation(BaseModel):
    signal_type: Literal["player_track"] = "player_track"
    candidate_id: str = Field(min_length=1)
    provenance: PredictionProvenance
    frame: FrameRef
    track_id: str | None = Field(default=None, min_length=1)
    bbox: BoundingBox
    person_role: PersonRole | None = None
    role_confidence: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    team: TeamSide | None = None
    team_confidence: float | None = Field(default=None, ge=0, le=1)
    # Jersey-color-clustering heuristic signal (volley_ml.detection.jersey_color)
    # -- true when this box's dominant torso color sits far from either
    # majority jersey-color cluster in its frame. Never asserts identity
    # (a libero, a referee in a colored shirt, and a color-clustering
    # false alarm all set this the same way); it only raises this
    # candidate's review priority. See PROFESSIONAL_ANNOTATION_PROTOCOL.md.
    jersey_color_outlier: bool = False
    review: ReviewAudit = Field(default_factory=ReviewAudit)

    @model_validator(mode="after")
    def _team_prediction_has_confidence(self) -> PlayerTrackPreannotation:
        if (self.team is None) != (self.team_confidence is None):
            raise ValueError("team and team_confidence must be provided together")
        if (self.person_role is None) != (self.role_confidence is None):
            raise ValueError("person_role and role_confidence must be provided together")
        return self


class BallFramePreannotation(BaseModel):
    signal_type: Literal["ball_frame"] = "ball_frame"
    candidate_id: str = Field(min_length=1)
    provenance: PredictionProvenance
    frame: FrameRef
    rally_id: str | None = None
    center_pixel: PixelPoint | None = None
    radius_px: float | None = Field(default=None, gt=0)
    visible_probability: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    temporal_source: TemporalSource = "observed"
    review: ReviewAudit = Field(default_factory=ReviewAudit)

    @model_validator(mode="after")
    def _radius_needs_a_center(self) -> BallFramePreannotation:
        if self.radius_px is not None and self.center_pixel is None:
            raise ValueError("ball radius requires a predicted center")
        return self


class PoseKeypointPreannotation(BaseModel):
    name: str
    visibility: KeypointVisibility
    pixel: PixelPoint | None = None
    confidence: float = Field(ge=0, le=1)

    @field_validator("name")
    @classmethod
    def _known_keypoint(cls, value: str) -> str:
        if value not in VOLLEY_SKELETON_KEYPOINTS:
            raise ValueError(f"unknown volleyball skeleton keypoint: {value}")
        return value

    @model_validator(mode="after")
    def _visibility_matches_point(self) -> PoseKeypointPreannotation:
        if self.visibility == "visible" and self.pixel is None:
            raise ValueError("visible keypoint requires a predicted pixel")
        if self.visibility == "outside_frame" and self.pixel is not None:
            raise ValueError("outside-frame keypoint cannot have a predicted pixel")
        return self


class PlayerPosePreannotation(BaseModel):
    signal_type: Literal["player_pose"] = "player_pose"
    candidate_id: str = Field(min_length=1)
    provenance: PredictionProvenance
    frame: FrameRef
    track_id: str = Field(min_length=1)
    bbox: BoundingBox
    keypoints: list[PoseKeypointPreannotation] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    review: ReviewAudit = Field(default_factory=ReviewAudit)

    @model_validator(mode="after")
    def _keypoints_are_unique(self) -> PlayerPosePreannotation:
        names = [keypoint.name for keypoint in self.keypoints]
        if len(names) != len(set(names)):
            raise ValueError("pose preannotation keypoint names must be unique")
        return self


class ContactPreannotation(BaseModel):
    signal_type: Literal["contact"] = "contact"
    candidate_id: str = Field(min_length=1)
    provenance: PredictionProvenance
    frame: FrameRef
    rally_id: str | None = None
    actor_track_id: str = Field(min_length=1)
    action_type: ActionType
    contact_surface: ContactSurface = "unknown"
    ball_center_pixel: PixelPoint
    confidence: float = Field(ge=0, le=1)
    actor_confidence: float = Field(ge=0, le=1)
    action_confidence: float = Field(ge=0, le=1)
    temporal_uncertainty_frames: int = Field(ge=0)
    review: ReviewAudit = Field(default_factory=ReviewAudit)

    @model_validator(mode="after")
    def _contact_is_not_a_phase(self) -> ContactPreannotation:
        if self.action_type == ActionType.TRANSITION:
            raise ValueError("transition cannot be proposed as a ball contact")
        return self


Preannotation = (
    PlayerTrackPreannotation
    | BallFramePreannotation
    | PlayerPosePreannotation
    | ContactPreannotation
)


def assert_review_created_ground_truth(item: Preannotation) -> str:
    """Return the linked GT id only when a reviewer created a separate label."""

    if item.review.status not in {"accepted", "corrected"} or not item.review.ground_truth_id:
        raise ValueError("preannotation has not produced separately reviewed ground truth")
    return item.review.ground_truth_id
