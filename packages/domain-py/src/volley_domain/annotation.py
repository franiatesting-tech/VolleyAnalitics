"""Annotation data shapes for the Phase 4 dataset factory -- court/player/
ball/action/pose/rally ground truth produced by human annotators in CVAT
(or curated/reviewed in FiftyOne), designed to round-trip with each tool's
own export format where practical (CVAT's "CVAT for video 1.1" XML;
FiftyOne's `Detection`/`Keypoint`/`Classification` label dict shapes).

Traceability (see CLAUDE.md's Traceability section, data-lineage skill):
an annotation produced by a human in CVAT is a **GroundTruth**, not a
Prediction -- distinct from the model-output rows already in
`volley_domain.ontology` (Action/Outcome/BallObservation/PlayerObservation,
which all carry `model_run_id`). `GroundTruthProvenance` is this module's
equivalent of that required-provenance block: every annotation here carries
back to an exact video, frame, dataset version, and annotator, exactly like
every Prediction row carries `source_video_id`/`pipeline_run_id`/etc.

These are plain Pydantic schemas, not new SQLAlchemy/Alembic tables. CVAT
and FiftyOne are themselves the systems of record for raw/working
annotation state (see docs/datasets/README.md for the setup) -- this module
is the normalized interchange shape the dataset factory's QA scripts,
splitter, and dataset-card generator (tools/dataset_factory) all operate
on, converted from/to CVAT and FiftyOne's own formats at the boundary. If a
future phase needs annotations queryable from services/api itself (not just
offline tooling), that's a new, deliberate ontology table decision -- not
assumed here, per CLAUDE.md's "no abstractions before they're needed."

Taxonomy reuse: action types and roster positions are imported directly
from `volley_domain.ontology` rather than re-declared here, so the
annotation vocabulary and the production Event Log vocabulary can never
silently drift apart.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from volley_domain.ontology import ActionType, RosterPosition

SourceTool = Literal["cvat", "fiftyone", "manual"]

COURT_KEYPOINT_NAMES = (
    "near_baseline_left",
    "near_baseline_right",
    "near_attack_line_left",
    "near_attack_line_right",
    "centerline_left",
    "centerline_right",
    "far_attack_line_left",
    "far_attack_line_right",
    "far_baseline_left",
    "far_baseline_right",
)

VOLLEY_SKELETON_KEYPOINTS = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_big_toe",
    "left_small_toe",
    "left_heel",
    "right_big_toe",
    "right_small_toe",
    "right_heel",
)

VOLLEY_SKELETON_EDGES = (
    ("nose", "left_eye"),
    ("nose", "right_eye"),
    ("left_eye", "left_ear"),
    ("right_eye", "right_ear"),
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
    ("left_ankle", "left_heel"),
    ("left_ankle", "left_big_toe"),
    ("left_big_toe", "left_small_toe"),
    ("right_ankle", "right_heel"),
    ("right_ankle", "right_big_toe"),
    ("right_big_toe", "right_small_toe"),
)

MeasurementMode = Literal[
    "image_2d",
    "court_plane",
    "monocular_physics",
    "monocular_size_prior",
    "triangulated",
    "manual",
]
KeypointVisibility = Literal["visible", "occluded", "outside_frame", "uncertain"]
TeamSide = Literal["home", "away"]
PersonRole = Literal["on_court_player", "substitute", "official", "staff", "spectator"]
ContactSurface = Literal[
    "left_hand",
    "right_hand",
    "both_hands",
    "forearms",
    "head",
    "foot",
    "other",
    "unknown",
]
ContactQuality = Literal["perfect", "positive", "neutral", "negative", "error", "unknown"]
Matrix3x3 = tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]


class GroundTruthProvenance(BaseModel):
    """The annotation-side equivalent of a Prediction row's required
    provenance fields (CLAUDE.md's Traceability section) -- every
    annotation below embeds one of these, not just a bare label."""

    organization_id: str = Field(min_length=1)
    video_id: str
    video_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    dataset_version: str
    annotator_id: str
    source_tool: SourceTool
    created_at: datetime
    reviewed: bool = False


class FrameRef(BaseModel):
    """Mirrors DATA_FLOW.md's rule that a frame is never referenced by
    frame number alone: both the proxy/source frame index used by the
    annotation tool and the normalized analysis timestamp it maps to."""

    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)


class BoundingBox(BaseModel):
    """Normalized (0-1) top-left + width/height -- FiftyOne's own
    `Detection.bounding_box` convention, adopted here directly so the
    to/from-FiftyOne converters below are a straight field mapping rather
    than a coordinate-system translation."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(ge=0, le=1)
    height: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _must_fit_inside_normalized_frame(self) -> BoundingBox:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("bounding box extends outside the normalized frame")
        return self


class CourtKeypointAnnotation(BaseModel):
    """One labeled court-line/corner keypoint, the ground truth court
    calibration (Phase 5's ml/court) will be evaluated against."""

    provenance: GroundTruthProvenance
    frame: FrameRef
    keypoint_name: str  # e.g. "sideline_near_left", "attack_line_far_right"
    x_pixel: float = Field(ge=0)
    y_pixel: float = Field(ge=0)
    visible: bool = True


class PlayerBBoxAnnotation(BaseModel):
    provenance: GroundTruthProvenance
    frame: FrameRef
    track_id: str = Field(min_length=1)  # stable across frames for the same physical player
    bbox: BoundingBox
    team: Literal["home", "away"] | None = None
    person_role: PersonRole = "on_court_player"
    jersey_number: int | None = Field(default=None, ge=0, le=99)
    position: RosterPosition | None = None
    occluded: bool = False
    truncated: bool = False


class BallAnnotation(BaseModel):
    """Ground truth for the ball pipeline (ml/ball). Unlike
    `BallObservation`'s observed/interpolated/predicted provenance (that
    distinction is meaningless for a human-labeled point -- a human either
    saw the ball in this frame or didn't), this only distinguishes visible
    vs. occluded, mirroring what an annotator can actually assert."""

    provenance: GroundTruthProvenance
    frame: FrameRef
    x_pixel: float | None
    y_pixel: float | None
    visible: bool  # False when the ball isn't visible in this frame at all

    @model_validator(mode="after")
    def _visible_ball_needs_coordinates(self) -> BallAnnotation:
        if self.visible and (self.x_pixel is None or self.y_pixel is None):
            raise ValueError("visible ball annotation requires x_pixel and y_pixel")
        if self.x_pixel is not None and self.x_pixel < 0:
            raise ValueError("x_pixel must be non-negative")
        if self.y_pixel is not None and self.y_pixel < 0:
            raise ValueError("y_pixel must be non-negative")
        return self


class PoseKeypoint(BaseModel):
    name: str  # COCO-17/RTMPose keypoint name, e.g. "left_wrist"
    x_pixel: float
    y_pixel: float
    visible: bool = True


class PoseAnnotation(BaseModel):
    provenance: GroundTruthProvenance
    frame: FrameRef
    track_id: str
    keypoints: list[PoseKeypoint] = Field(min_length=1)

    @model_validator(mode="after")
    def _keypoint_names_are_unique(self) -> PoseAnnotation:
        names = [keypoint.name for keypoint in self.keypoints]
        if len(names) != len(set(names)):
            raise ValueError("pose keypoint names must be unique")
        return self


class ActionAnnotation(BaseModel):
    """Ground truth for action recognition (Phase 6) -- an annotator-
    labeled action span, distinct from `volley_domain.ontology.Action`
    (which is a model/pipeline-produced Prediction row with
    `model_run_id`, never a human annotation)."""

    provenance: GroundTruthProvenance
    action_type: ActionType
    start_frame: FrameRef
    end_frame: FrameRef
    actor_track_id: str | None = None

    @model_validator(mode="after")
    def _action_span_is_forward(self) -> ActionAnnotation:
        if self.end_frame.frame_index < self.start_frame.frame_index:
            raise ValueError("action end_frame precedes start_frame")
        if self.end_frame.timestamp_seconds < self.start_frame.timestamp_seconds:
            raise ValueError("action end timestamp precedes start timestamp")
        return self


class RallyBoundaryAnnotation(BaseModel):
    provenance: GroundTruthProvenance
    set_index: int = Field(ge=1)
    rally_index_in_set: int = Field(ge=1)
    start_frame: FrameRef
    end_frame: FrameRef

    @model_validator(mode="after")
    def _rally_span_is_forward(self) -> RallyBoundaryAnnotation:
        if self.end_frame.frame_index < self.start_frame.frame_index:
            raise ValueError("rally end_frame precedes start_frame")
        if self.end_frame.timestamp_seconds < self.start_frame.timestamp_seconds:
            raise ValueError("rally end timestamp precedes start timestamp")
        return self


class PixelPoint(BaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)


class WorldPoint3D(BaseModel):
    """Metric court coordinates.

    Origin is the near-left court corner viewed from the calibrated camera:
    x runs across the 9 m court, y toward the far baseline over 18 m, and z
    points upward. Expanded bounds allow serves and defensive play outside
    the lines while rejecting unit/axis mistakes early.
    """

    x_m: float = Field(ge=-9, le=18)
    y_m: float = Field(ge=-18, le=36)
    z_m: float = Field(ge=0, le=30)


class Vector3D(BaseModel):
    x: float
    y: float
    z: float


class WorldUncertainty(BaseModel):
    x_std_m: float = Field(gt=0)
    y_std_m: float = Field(gt=0)
    z_std_m: float = Field(gt=0)


class SpatialEstimate3D(BaseModel):
    point: WorldPoint3D
    measurement_mode: MeasurementMode
    confidence: float = Field(ge=0, le=1)
    uncertainty: WorldUncertainty
    reprojection_error_px: float | None = Field(default=None, ge=0)
    camera_ids: list[str] = Field(min_length=1)
    calibration_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _triangulation_needs_two_cameras(self) -> SpatialEstimate3D:
        if self.measurement_mode == "triangulated" and len(set(self.camera_ids)) < 2:
            raise ValueError("triangulated 3D requires at least two distinct cameras")
        return self


class ScalarMeasurement(BaseModel):
    value: float | None = None
    unit: str = Field(min_length=1)
    measurement_mode: MeasurementMode
    confidence: float = Field(ge=0, le=1)
    uncertainty: float | None = Field(default=None, ge=0)
    status: Literal["measured", "estimated", "abstained"]
    abstention_reason: str | None = None
    supporting_frames: list[FrameRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _abstention_is_explicit(self) -> ScalarMeasurement:
        if self.status == "abstained":
            if self.value is not None or not self.abstention_reason:
                raise ValueError("abstained measurements need no value and a reason")
        elif self.value is None:
            raise ValueError("measured/estimated measurements require a value")
        return self


class CameraCalibrationAnnotation(BaseModel):
    provenance: GroundTruthProvenance
    calibration_id: str = Field(min_length=1)
    frame: FrameRef
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    court_width_m: float = Field(default=9.0, gt=0)
    court_length_m: float = Field(default=18.0, gt=0)
    net_height_m: float = Field(gt=0)
    calibration_mode: Literal["automatic", "manual", "hybrid"]
    homography_image_to_court: Matrix3x3
    camera_matrix: Matrix3x3 | None = None
    rotation_world_to_camera: Matrix3x3 | None = None
    translation_world_to_camera_m: tuple[float, float, float] | None = None
    distortion_coefficients: list[float] = Field(default_factory=list)
    labelled_keypoint_count: int = Field(ge=4)
    reprojection_error_px: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    supports_metric_3d: bool = False

    @model_validator(mode="after")
    def _metric_3d_needs_full_camera_model(self) -> CameraCalibrationAnnotation:
        camera_model = (
            self.camera_matrix,
            self.rotation_world_to_camera,
            self.translation_world_to_camera_m,
        )
        if self.supports_metric_3d and any(value is None for value in camera_model):
            raise ValueError("metric 3D calibration requires intrinsics and extrinsics")
        return self


class BallFrameAnnotation(BaseModel):
    provenance: GroundTruthProvenance
    frame: FrameRef
    rally_id: str = Field(min_length=1)
    visibility: KeypointVisibility
    center_pixel: PixelPoint | None = None
    radius_px: float | None = Field(default=None, gt=0)
    world_3d: SpatialEstimate3D | None = None
    motion_blurred: bool = False
    truncated: bool = False

    @model_validator(mode="after")
    def _visibility_matches_coordinates(self) -> BallFrameAnnotation:
        if self.visibility == "visible" and self.center_pixel is None:
            raise ValueError("visible ball requires a pixel center")
        if self.visibility == "outside_frame" and self.center_pixel is not None:
            raise ValueError("outside-frame ball cannot have a pixel center")
        return self


class PoseKeypointMeasurement(BaseModel):
    name: str
    visibility: KeypointVisibility
    pixel: PixelPoint | None = None
    world_3d: SpatialEstimate3D | None = None

    @field_validator("name")
    @classmethod
    def _known_volleyball_keypoint(cls, value: str) -> str:
        if value not in VOLLEY_SKELETON_KEYPOINTS:
            raise ValueError(f"unknown volleyball skeleton keypoint: {value}")
        return value

    @model_validator(mode="after")
    def _visible_keypoint_has_pixel(self) -> PoseKeypointMeasurement:
        if self.visibility == "visible" and self.pixel is None:
            raise ValueError("visible pose keypoint requires pixel coordinates")
        if self.visibility == "outside_frame" and self.pixel is not None:
            raise ValueError("outside-frame keypoint cannot have pixel coordinates")
        return self


class PlayerPoseFrameAnnotation(BaseModel):
    provenance: GroundTruthProvenance
    frame: FrameRef
    rally_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    team: TeamSide
    bbox: BoundingBox
    skeleton_definition: Literal["volley_coco_wholebody_body_foot_v1"] = (
        "volley_coco_wholebody_body_foot_v1"
    )
    keypoints: list[PoseKeypointMeasurement] = Field(min_length=1)
    foot_anchor_world: SpatialEstimate3D | None = None

    @model_validator(mode="after")
    def _keypoints_are_unique(self) -> PlayerPoseFrameAnnotation:
        names = [keypoint.name for keypoint in self.keypoints]
        if len(names) != len(set(names)):
            raise ValueError("pose keypoint names must be unique per player/frame")
        return self


class BallContactAnnotation(BaseModel):
    provenance: GroundTruthProvenance
    contact_id: str = Field(min_length=1)
    rally_id: str = Field(min_length=1)
    contact_index: int = Field(ge=1)
    frame: FrameRef
    team: TeamSide
    actor_track_id: str = Field(min_length=1)
    action_type: ActionType
    contact_surface: ContactSurface = "unknown"
    quality: ContactQuality = "unknown"
    ball_center_pixel: PixelPoint
    # The floor point directly beneath the contact/actor, in image pixels
    # -- NOT the ball's own aerial position. A homography only maps points
    # on one plane (the court floor); it cannot correctly place a ball
    # 1-3 m in the air just because a matrix exists. See
    # PROFESSIONAL_ANNOTATION_PROTOCOL.md's "Contact point convention" --
    # this field is what that section actually refers to. Never conflate
    # it with `ball_center_pixel` above, which is the ball's real visible
    # position and must never be overwritten with a ground-projected
    # value. Optional: a reviewer may not always be able to estimate a
    # confident floor point (e.g. no calibration exists yet for this
    # camera segment), in which case court-plane math for this contact is
    # simply unavailable until it's filled in.
    contact_ground_pixel: PixelPoint | None = None
    ball_world_3d: SpatialEstimate3D | None = None
    contact_height: ScalarMeasurement | None = None
    incoming_velocity_mps: Vector3D | None = None
    outgoing_velocity_mps: Vector3D | None = None
    target_track_id: str | None = None
    target_court_point: WorldPoint3D | None = None

    @model_validator(mode="after")
    def _is_a_real_ball_contact(self) -> BallContactAnnotation:
        if self.action_type == ActionType.TRANSITION:
            raise ValueError("transition is a phase, not a ball contact")
        if self.contact_height and self.contact_height.unit != "m":
            raise ValueError("contact height must use metres")
        return self


class RallyGroundTruth(BaseModel):
    provenance: GroundTruthProvenance
    rally_id: str = Field(min_length=1)
    set_index: int = Field(ge=1, le=5)
    rally_index_in_set: int = Field(ge=1)
    start_frame: FrameRef
    end_frame: FrameRef
    serving_team: TeamSide
    point_winner_team: TeamSide | None = None
    score_before_home: int = Field(ge=0)
    score_before_away: int = Field(ge=0)
    complete_coverage: bool = True
    contacts: list[BallContactAnnotation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_contact_sequence(self) -> RallyGroundTruth:
        if self.end_frame.frame_index < self.start_frame.frame_index:
            raise ValueError("rally end frame precedes start frame")
        ordered = sorted(self.contacts, key=lambda contact: contact.contact_index)
        if [contact.contact_index for contact in ordered] != list(range(1, len(ordered) + 1)):
            raise ValueError("contact indexes must be contiguous and start at 1")
        if self.contacts != ordered:
            raise ValueError("contacts must be stored in contact order")
        if self.complete_coverage and ordered and ordered[0].action_type != ActionType.SERVE:
            raise ValueError("a complete rally must begin with a serve contact")

        last_frame = self.start_frame.frame_index
        current_team: TeamSide | None = None
        counted_touches = 0
        for contact in ordered:
            if contact.rally_id != self.rally_id:
                raise ValueError("contact rally_id does not match its rally")
            if contact.provenance.video_id != self.provenance.video_id:
                raise ValueError("contact and rally must reference the same video")
            if not (
                self.start_frame.frame_index
                <= contact.frame.frame_index
                <= self.end_frame.frame_index
            ):
                raise ValueError("contact frame lies outside rally boundaries")
            if contact.frame.frame_index < last_frame:
                raise ValueError("contact frames must be monotonic")
            last_frame = contact.frame.frame_index

            if contact.team != current_team:
                current_team = contact.team
                counted_touches = 0
            if contact.action_type != ActionType.BLOCK:
                counted_touches += 1
                if counted_touches > 3:
                    raise ValueError("more than three counted team contacts in one possession")
        return self


BiomechanicalMetricName = Literal[
    "jump_height",
    "contact_height",
    "block_reach_height",
    "approach_speed",
    "takeoff_vertical_velocity",
    "approach_step_count",
    "knee_flexion_takeoff",
    "knee_flexion_landing",
    "trunk_inclination",
    "shoulder_abduction",
    "elbow_extension",
    "arm_swing_angular_velocity",
    "hip_shoulder_separation",
    "landing_asymmetry_2d",
]


class BiomechanicalMetricAnnotation(BaseModel):
    provenance: GroundTruthProvenance
    metric_name: BiomechanicalMetricName
    track_id: str = Field(min_length=1)
    rally_id: str = Field(min_length=1)
    action_contact_id: str | None = None
    phase_start: FrameRef
    phase_end: FrameRef
    side: Literal["left", "right", "bilateral", "not_applicable"]
    measurement: ScalarMeasurement

    @model_validator(mode="after")
    def _phase_is_forward(self) -> BiomechanicalMetricAnnotation:
        if self.phase_end.frame_index < self.phase_start.frame_index:
            raise ValueError("biomechanical phase end precedes its start")
        return self


# ---------------------------------------------------------------------------
# CVAT round-trip ("CVAT for video 1.1" XML -- CVAT's own native export
# format for tracked annotations, verified against real CVAT-exported XML
# structure: <annotations><track id label><box frame xtl ytl xbr ybr
# outside occluded keyframe/></track></annotations>)
# ---------------------------------------------------------------------------


def cvat_task_labels_config(
    *,
    include_actions: bool = True,
    include_court: bool = False,
    include_rallies: bool = False,
    include_pose: bool = False,
    include_contacts: bool = False,
    include_biomechanics: bool = False,
) -> list[dict]:
    """The CVAT task label spec (JSON, as CVAT's task-creation API/UI
    expects) for this project's player/ball/action taxonomy -- generated
    from the same enums the production Event Log uses
    (`volley_domain.ontology`), so a CVAT annotation task is never
    hand-configured with a taxonomy that can drift from the real one."""
    labels = [
        {
            "name": "player",
            "attributes": [
                {"name": "team", "input_type": "select", "values": ["home", "away"]},
                {
                    "name": "person_role",
                    "input_type": "select",
                    "values": [
                        "on_court_player",
                        "substitute",
                        "official",
                        "staff",
                        "spectator",
                    ],
                },
                {"name": "jersey_number", "input_type": "number", "values": ["0", "99", "1"]},
                {
                    "name": "position",
                    "input_type": "select",
                    "values": [p.value for p in RosterPosition],
                },
                {"name": "truncated", "input_type": "checkbox", "values": ["false"]},
            ],
        },
        {"name": "ball", "attributes": []},
    ]
    if include_actions:
        labels.append(
            {
                "name": "action",
                "attributes": [
                    {
                        "name": "action_type",
                        "input_type": "select",
                        "values": [a.value for a in ActionType],
                    }
                ],
            }
        )
    if include_court:
        labels.append(
            {
                "name": "court_keypoint",
                "attributes": [
                    {
                        "name": "keypoint_name",
                        "input_type": "select",
                        "values": list(COURT_KEYPOINT_NAMES),
                    }
                ],
            }
        )
    if include_rallies:
        labels.append(
            {
                "name": "rally",
                "attributes": [
                    {"name": "set_index", "input_type": "number", "values": ["1", "5", "1"]},
                    {
                        "name": "rally_index",
                        "input_type": "number",
                        "values": ["1", "99", "1"],
                    },
                ],
            }
        )
    if include_pose:
        labels.append(
            {
                "name": "pose_keypoint",
                "type": "points",
                "attributes": [
                    {
                        "name": "keypoint_name",
                        "input_type": "select",
                        "values": list(VOLLEY_SKELETON_KEYPOINTS),
                    },
                    {"name": "track_id", "input_type": "text", "values": []},
                    {
                        "name": "visibility",
                        "input_type": "select",
                        "values": ["visible", "occluded", "uncertain"],
                    },
                ],
            }
        )
    if include_contacts:
        labels.append(
            {
                "name": "ball_contact",
                "type": "tag",
                "attributes": [
                    {
                        "name": "action_type",
                        "input_type": "select",
                        "values": [
                            action.value for action in ActionType if action != ActionType.TRANSITION
                        ],
                    },
                    {
                        "name": "contact_surface",
                        "input_type": "select",
                        "values": [
                            "left_hand",
                            "right_hand",
                            "both_hands",
                            "forearms",
                            "head",
                            "foot",
                            "other",
                            "unknown",
                        ],
                    },
                    {"name": "team", "input_type": "select", "values": ["home", "away"]},
                    {"name": "actor_track_id", "input_type": "text", "values": []},
                ],
            }
        )
    if include_biomechanics:
        labels.append(
            {
                "name": "biomechanics_phase",
                "type": "tag",
                "attributes": [
                    {
                        "name": "metric_name",
                        "input_type": "select",
                        "values": [
                            "jump_height",
                            "contact_height",
                            "block_reach_height",
                            "approach_speed",
                            "takeoff_vertical_velocity",
                            "knee_flexion_takeoff",
                            "knee_flexion_landing",
                            "trunk_inclination",
                            "shoulder_abduction",
                            "elbow_extension",
                            "arm_swing_angular_velocity",
                            "hip_shoulder_separation",
                            "landing_asymmetry_2d",
                        ],
                    },
                    {"name": "track_id", "input_type": "text", "values": []},
                    {
                        "name": "side",
                        "input_type": "select",
                        "values": ["left", "right", "bilateral", "not_applicable"],
                    },
                ],
            }
        )
    return labels


def _cvat_attr(box_el: ET.Element, name: str) -> str | None:
    for attr in box_el.findall("attribute"):
        if attr.get("name") == name:
            return attr.text
    return None


def parse_cvat_video_xml(
    xml_text: str,
    *,
    provenance: GroundTruthProvenance,
    fps: float,
    frame_width: float,
    frame_height: float,
) -> list[PlayerBBoxAnnotation]:
    """Parses player bounding-box tracks out of a "CVAT for video 1.1"
    export. Only the `player`-labeled tracks are extracted here (ball/pose
    tracks use CVAT's differently-shaped `points`/`polyline` elements, not
    `box` -- out of scope for this function). `outside="1"` boxes (CVAT's
    marker for "track paused/not present in this frame") are skipped,
    matching how CVAT itself treats them as absent, not a real zero-size
    detection.

    CVAT's native `box` coordinates are pixels in the source frame, but
    `BoundingBox` (this module's normalized-coordinate type, matching
    FiftyOne's convention) is 0-1 -- `frame_width`/`frame_height` are
    required so this function can actually normalize rather than silently
    accept pixel values that would violate BoundingBox's own [0,1]
    constraint (caught by this module's own test suite: a naive first
    draft skipped normalization and broke on any real, non-degenerate box)."""
    root = ET.fromstring(xml_text)
    results: list[PlayerBBoxAnnotation] = []

    for track in root.findall(".//track[@label='player']"):
        track_id = track.get("id", "")
        for box in track.findall("box"):
            if box.get("outside") == "1":
                continue
            frame_index = int(box.get("frame", "0"))
            xtl, ytl, xbr, ybr = (
                float(box.get("xtl", "0")),
                float(box.get("ytl", "0")),
                float(box.get("xbr", "0")),
                float(box.get("ybr", "0")),
            )

            jersey_raw = _cvat_attr(box, "jersey_number")
            team_raw = _cvat_attr(box, "team")
            position_raw = _cvat_attr(box, "position")
            person_role_raw = _cvat_attr(box, "person_role")

            results.append(
                PlayerBBoxAnnotation(
                    provenance=provenance,
                    frame=FrameRef(frame_index=frame_index, timestamp_seconds=frame_index / fps),
                    track_id=track_id,
                    bbox=BoundingBox(
                        x=xtl / frame_width,
                        y=ytl / frame_height,
                        width=(xbr - xtl) / frame_width,
                        height=(ybr - ytl) / frame_height,
                    ),
                    team=team_raw if team_raw in ("home", "away") else None,
                    person_role=person_role_raw
                    if person_role_raw
                    in ("on_court_player", "substitute", "official", "staff", "spectator")
                    else "on_court_player",
                    jersey_number=int(jersey_raw) if jersey_raw and jersey_raw.isdigit() else None,
                    position=RosterPosition(position_raw)
                    if position_raw in {p.value for p in RosterPosition}
                    else None,
                    occluded=_cvat_attr(box, "occluded") == "true" or box.get("occluded") == "1",
                    truncated=_cvat_attr(box, "truncated") == "true",
                )
            )
    return results


def player_bbox_annotations_to_cvat_video_xml(
    annotations: list[PlayerBBoxAnnotation],
    *,
    frame_width: float,
    frame_height: float,
    task_name: str = "volley-annotation-task",
) -> str:
    """Inverse of parse_cvat_video_xml -- exports our normalized (0-1)
    shape back to CVAT's native pixel-coordinate XML, so a QA/relabeling
    round trip (export -> QA script flags issues -> re-import for
    correction) is possible without a lossy intermediate format.
    `frame_width`/`frame_height` must match the same source video's
    dimensions used when the annotations were originally parsed in, or the
    round trip will silently scale boxes incorrectly."""
    root = ET.Element("annotations")
    ET.SubElement(root, "version").text = "1.1"
    meta = ET.SubElement(root, "meta")
    task = ET.SubElement(meta, "task")
    ET.SubElement(task, "name").text = task_name

    by_track: dict[str, list[PlayerBBoxAnnotation]] = {}
    for ann in annotations:
        by_track.setdefault(ann.track_id, []).append(ann)

    for track_id, track_annotations in by_track.items():
        track_el = ET.SubElement(root, "track", id=track_id, label="player")
        for ann in sorted(track_annotations, key=lambda a: a.frame.frame_index):
            xtl = ann.bbox.x * frame_width
            ytl = ann.bbox.y * frame_height
            xbr = (ann.bbox.x + ann.bbox.width) * frame_width
            ybr = (ann.bbox.y + ann.bbox.height) * frame_height
            box_el = ET.SubElement(
                track_el,
                "box",
                frame=str(ann.frame.frame_index),
                xtl=str(xtl),
                ytl=str(ytl),
                xbr=str(xbr),
                ybr=str(ybr),
                outside="0",
                occluded="1" if ann.occluded else "0",
                keyframe="1",
            )
            if ann.team:
                ET.SubElement(box_el, "attribute", name="team").text = ann.team
            ET.SubElement(box_el, "attribute", name="person_role").text = ann.person_role
            if ann.jersey_number is not None:
                ET.SubElement(box_el, "attribute", name="jersey_number").text = str(
                    ann.jersey_number
                )
            if ann.position:
                ET.SubElement(box_el, "attribute", name="position").text = ann.position.value
            ET.SubElement(box_el, "attribute", name="truncated").text = str(ann.truncated).lower()

    return ET.tostring(root, encoding="unicode")


# ---------------------------------------------------------------------------
# FiftyOne round-trip (pure dict shapes matching fiftyone.core.labels'
# documented Detection/Keypoint field layout -- no dependency on the
# `fiftyone` package itself, kept a heavy, optional tool dependency
# confined to tools/dataset_factory, see that package's own pyproject.toml)
# ---------------------------------------------------------------------------


def player_bbox_to_fiftyone_detection(ann: PlayerBBoxAnnotation, *, label: str = "player") -> dict:
    return {
        "_cls": "Detection",
        "label": label,
        "bounding_box": [ann.bbox.x, ann.bbox.y, ann.bbox.width, ann.bbox.height],
        "index": ann.track_id,
        "attributes": {
            "team": ann.team,
            "person_role": ann.person_role,
            "jersey_number": ann.jersey_number,
            "position": ann.position.value if ann.position else None,
            "occluded": ann.occluded,
            "truncated": ann.truncated,
            "annotator_id": ann.provenance.annotator_id,
            "dataset_version": ann.provenance.dataset_version,
        },
    }


def fiftyone_detection_to_player_bbox(
    detection: dict, *, provenance: GroundTruthProvenance, frame: FrameRef
) -> PlayerBBoxAnnotation:
    x, y, w, h = detection["bounding_box"]
    attrs = detection.get("attributes", {}) or {}
    position_raw = attrs.get("position")
    return PlayerBBoxAnnotation(
        provenance=provenance,
        frame=frame,
        track_id=str(detection.get("index", "")),
        bbox=BoundingBox(x=x, y=y, width=w, height=h),
        team=attrs.get("team"),
        person_role=attrs.get("person_role", "on_court_player"),
        jersey_number=attrs.get("jersey_number"),
        position=RosterPosition(position_raw)
        if position_raw in {p.value for p in RosterPosition}
        else None,
        occluded=bool(attrs.get("occluded", False)),
        truncated=bool(attrs.get("truncated", False)),
    )


# ---------------------------------------------------------------------------
# Track-based roster-position propagation -- cuts the human labeling burden
# from "once per frame" to "once per track" for the one player attribute
# that genuinely doesn't change frame-to-frame within a clip.
# ---------------------------------------------------------------------------


class ConflictingTrackPositionError(ValueError):
    """Raised when the same (video_id, track_id) carries two different
    reviewed roster positions -- a real data problem (a mislabel, or a
    track_id silently reused for two different physical players, which
    the protocol explicitly forbids: "never recycle an ID"), never
    something to silently resolve by picking one."""


def propagate_roster_position_by_track(
    annotations: list[PlayerBBoxAnnotation],
) -> list[PlayerBBoxAnnotation]:
    """A player's specialized roster position (OH/OP/MB/S/L) is fixed for
    the whole match -- it is not a per-frame fact like their current court
    zone, which changes every rotation. Once a human reviews and confirms
    it for a single frame of a given `track_id`, every other frame's box
    for that same physical player (same `provenance.video_id` +
    `track_id`) can safely inherit it, rather than requiring a human to
    re-label the same player's position in every frame of the clip.

    Only propagates from a *reviewed* source (`provenance.reviewed=True`)
    -- an unreviewed model guess must never fan out and quietly become the
    position recorded for dozens of other frames. Never overwrites a
    position a human already set on the target frame (a human's own label
    always wins over a propagated one, reviewed or not). Raises
    `ConflictingTrackPositionError` if two *reviewed* annotations for the
    same track disagree, rather than silently picking one -- see that
    exception's docstring for why this is a real problem to surface, not
    paper over.

    Pure function: returns a new list, never mutates its input (matches
    this module's Pydantic-model-are-immutable-by-convention style)."""
    confirmed_position_by_track: dict[tuple[str, str], RosterPosition] = {}
    for ann in annotations:
        if not (ann.provenance.reviewed and ann.position is not None):
            continue
        key = (ann.provenance.video_id, ann.track_id)
        existing = confirmed_position_by_track.get(key)
        if existing is not None and existing != ann.position:
            raise ConflictingTrackPositionError(
                f"track {ann.track_id!r} in video {ann.provenance.video_id!r} has "
                f"conflicting reviewed positions: {existing!r} and {ann.position!r}"
            )
        confirmed_position_by_track[key] = ann.position

    results: list[PlayerBBoxAnnotation] = []
    for ann in annotations:
        if ann.position is not None:
            results.append(ann)
            continue
        confirmed = confirmed_position_by_track.get((ann.provenance.video_id, ann.track_id))
        results.append(ann.model_copy(update={"position": confirmed}) if confirmed else ann)
    return results
