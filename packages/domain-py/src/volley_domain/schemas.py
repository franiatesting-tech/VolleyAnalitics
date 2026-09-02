"""Pydantic v2 schemas: the API contract. FastAPI's OpenAPI spec is generated
directly from these -- see packages/contracts, which turns that spec into
TypeScript types/client. Never hand-duplicate these shapes in TypeScript.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from volley_domain.analysis import RallyAnalysisBundle
from volley_domain.annotation import COURT_KEYPOINT_NAMES
from volley_domain.court import Zone

# ---------------------------------------------------------------------------
# Matches / jobs (persisted, API-facing)
# ---------------------------------------------------------------------------


class MatchStatus(StrEnum):
    draft = "draft"
    demo_ready = "demo_ready"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class MatchCreate(BaseModel):
    home_team: str = Field(min_length=1, max_length=255)
    away_team: str = Field(min_length=1, max_length=255)
    scheduled_at: datetime | None = None


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    home_team: str
    away_team: str
    # Nullable: real Team rows only exist once a real roster/synthetic
    # demo has been persisted against this match (see
    # synthetic/persistence.py) -- a freshly created Match legitimately
    # has neither yet. The frontend must not assume these are always
    # present; see docs/domain/ONTOLOGY.md's "Match structure" section.
    home_team_id: str | None
    away_team_id: str | None
    scheduled_at: datetime | None
    status: MatchStatus
    created_at: datetime
    updated_at: datetime


class ProcessingJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    match_id: str
    task_name: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    stage: str | None
    attempt: int
    result_data: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Synthetic match data (Prompt 1 stand-in for the real Event Log -- the
# full ontology from ADR-003/Prompt 2 will supersede this shape; kept
# intentionally simple and clearly labeled "synthetic" so it's never
# confused for a real Prediction/Event.)
# ---------------------------------------------------------------------------

Team = Literal["home", "away"]
RosterPosition = Literal["OH", "OP", "MB", "S", "L"]
BallProvenance = Literal["observed", "interpolated", "predicted"]
ActionType = Literal[
    "serve", "reception", "set", "attack", "tip", "block", "dig", "free_ball", "transition"
]
ActionOutcome = Literal["continue", "point", "error"]


class RosterPlayer(BaseModel):
    id: str
    name: str
    jersey_number: int
    position: RosterPosition


class TeamRoster(BaseModel):
    team_name: str
    players: list[RosterPlayer]


class PlayerPositionSample(BaseModel):
    t: float  # seconds from rally start
    player_id: str
    team: Team
    x: float = Field(ge=0.0, le=1.0)  # normalized court coordinates, see DATA_FLOW.md
    y: float = Field(ge=0.0, le=1.0)


class BallPositionSample(BaseModel):
    t: float
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    z: float = Field(ge=0.0, description="normalized height, 0 = floor")
    provenance: BallProvenance
    confidence: float = Field(ge=0.0, le=1.0)


class SyntheticAction(BaseModel):
    id: str
    t_start: float
    t_end: float
    type: ActionType
    actor_player_id: str
    actor_team: Team
    outcome: ActionOutcome
    # Mirrors Outcome.detail -- e.g. "blocked" for an attack error caused
    # by an opposing block stuff, so compute_attack_stats can read it
    # directly instead of inferring from action adjacency. See
    # TECH_DEBT.md's now-fixed "blocked attack heuristic never exercised"
    # entry.
    detail: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    court_x: float = Field(ge=0.0, le=1.0)
    court_y: float = Field(ge=0.0, le=1.0)


class SyntheticRally(BaseModel):
    id: str
    index_in_set: int
    serving_team: Team
    point_winner: Team
    actions: list[SyntheticAction]
    player_positions: list[PlayerPositionSample]
    ball_positions: list[BallPositionSample]
    duration_seconds: float
    # Cumulative offset within the synthetic match's own timeline (seconds
    # from the start of set 1) -- NOT a real video PTS (there is no real
    # video). Named match_t_* rather than video_t_* deliberately, so it's
    # never confused with the absolute-video-time contract Rally.video_t_*
    # carries in the real ontology (see ONTOLOGY.md / DATA_FLOW.md).
    # persist_synthetic_match writes these into Rally.video_t_start/end as
    # the best available stand-in until real video timing exists (Phase 5+).
    # An earlier version reset each rally's actions to start at t=0, so
    # every rally in a multi-set match claimed the same ~0-12s window --
    # caught by independent architecture review.
    match_t_start: float
    match_t_end: float


class SyntheticSetScore(BaseModel):
    home_points: int
    away_points: int
    winner: Team


class SyntheticSet(BaseModel):
    index: int
    score: SyntheticSetScore
    rallies: list[SyntheticRally]


class SyntheticMatchSummary(BaseModel):
    """Small, cheap-to-render summary of a SyntheticMatch, without shipping
    every rally's full position time series. NOT currently used by any API
    route -- `GET /matches/{id}/result` returns the full SyntheticMatch (see
    ADR-002: the frontend needs full rally/position data). Kept for a future
    lightweight summary view (e.g. a matches-list card) where the full
    payload would be wasteful; delete if that need never materializes."""

    seed: int
    home_team: str
    away_team: str
    sets_won_home: int
    sets_won_away: int
    set_scores: list[SyntheticSetScore]
    total_rallies: int
    generated_at: datetime


class SyntheticMatch(BaseModel):
    # Fixed marker, not a configurable flag: this payload's provenance must
    # survive being copied, cached, or consumed by something other than the
    # one UI card that currently captions it "synthetic demo output" -- a
    # future consumer that only sees the JSON should never be able to
    # mistake this for a real Prediction (see DATA_FLOW.md's entity
    # separation rule).
    synthetic: Literal[True] = True
    seed: int
    home_roster: TeamRoster
    away_roster: TeamRoster
    sets: list[SyntheticSet]
    generated_at: datetime

    def summary(self) -> SyntheticMatchSummary:
        sets_won_home = sum(1 for s in self.sets if s.score.winner == "home")
        sets_won_away = sum(1 for s in self.sets if s.score.winner == "away")
        return SyntheticMatchSummary(
            seed=self.seed,
            home_team=self.home_roster.team_name,
            away_team=self.away_roster.team_name,
            sets_won_home=sets_won_home,
            sets_won_away=sets_won_away,
            set_scores=[s.score for s in self.sets],
            total_rallies=sum(len(s.rallies) for s in self.sets),
            generated_at=self.generated_at,
        )


# ---------------------------------------------------------------------------
# Ontology read API (Phase 2, see docs/domain/ONTOLOGY.md) -- response
# shapes for the real persisted Event Log, distinct from the Synthetic*
# schemas above (which describe the Phase 1 JSON-blob demo payload).
# ---------------------------------------------------------------------------


class MatchSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    match_id: str
    index: int
    home_points: int
    away_points: int
    winner_team_id: str | None
    created_at: datetime


class RallyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    set_id: str
    index_in_set: int
    serving_team_id: str
    point_winner_team_id: str | None
    video_t_start: float | None
    video_t_end: float | None
    duration_seconds: float | None


class RallyAnalysisResultOut(BaseModel):
    """One immutable, completed professional analysis snapshot."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    match_id: str
    rally_id: str
    video_id: str
    pipeline_run_id: str
    schema_version: str
    content_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    bundle: RallyAnalysisBundle = Field(validation_alias="bundle_data")
    created_at: datetime


class OutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    result: ActionOutcome
    detail: str | None


class ActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    phase_id: str
    rally_id: str
    action_type: ActionType
    actor_team_id: str
    actor_roster_id: str | None
    video_t_start: float
    video_t_end: float
    court_x: float
    court_y: float
    confidence: float
    reviewed_status: Literal["unreviewed", "confirmed", "corrected"]
    quality_rating: int | None
    outcome: OutcomeOut | None = None


class ServeStatsOut(BaseModel):
    team_id: str
    total_serves: int = Field(ge=0)
    aces: int = Field(ge=0)
    serve_errors: int = Field(ge=0)
    zone_counts: dict[Zone, int]


class ReceptionStatsOut(BaseModel):
    team_id: str
    total_receptions: int = Field(ge=0)
    rated_receptions: int = Field(ge=0)
    average_rating: float | None
    is_effective: bool | None


class AttackStatsOut(BaseModel):
    team_id: str
    total_attacks: int = Field(ge=0)
    kills: int = Field(ge=0)
    errors: int = Field(ge=0)
    blocked: int = Field(ge=0)
    efficiency: float | None
    zone_counts: dict[Zone, int]
    takeoff_position_counts: dict[Literal["left", "middle", "right"], int]


class BlockStatsOut(BaseModel):
    team_id: str
    total_blocks: int = Field(ge=0)
    block_kills: int = Field(ge=0)
    block_errors: int = Field(ge=0)


class DigStatsOut(BaseModel):
    team_id: str
    total_digs: int = Field(ge=0)


class SideoutBreakpointStatsOut(BaseModel):
    team_id: str
    serve_rallies: int = Field(ge=0)
    serve_points_won: int = Field(ge=0)
    breakpoint_pct: float | None = Field(ge=0, le=1)
    reception_rallies: int = Field(ge=0)
    reception_points_won: int = Field(ge=0)
    sideout_pct: float | None = Field(ge=0, le=1)


class SetterDistributionEntryOut(BaseModel):
    setter_roster_id: str
    total_sets: int = Field(ge=0)
    followed_by_attack: int = Field(ge=0)
    zone_counts: dict[Zone, int]


class RallyDurationStatsOut(BaseModel):
    count: int = Field(ge=0)
    mean_seconds: float | None = Field(ge=0)
    median_seconds: float | None = Field(ge=0)
    min_seconds: float | None = Field(ge=0)
    max_seconds: float | None = Field(ge=0)


class MatchStatisticsOut(BaseModel):
    """Versioned, fully typed public contract for every computed metric.

    The pure engine remains the formula source of truth; these models make
    shape changes visible in OpenAPI and therefore at TypeScript compile
    time instead of failing inside a chart at runtime.
    """

    formula_version: str
    serve: dict[str, ServeStatsOut]
    reception: dict[str, ReceptionStatsOut]
    attack: dict[str, AttackStatsOut]
    block: dict[str, BlockStatsOut]
    dig: dict[str, DigStatsOut]
    sideout_breakpoint: dict[str, SideoutBreakpointStatsOut]
    setter_distribution: dict[str, SetterDistributionEntryOut]
    rally_duration: RallyDurationStatsOut


class StatCategory(StrEnum):
    serve_total = "serve_total"
    serve_aces = "serve_aces"
    serve_errors = "serve_errors"
    reception_total = "reception_total"
    attack_total = "attack_total"
    attack_kills = "attack_kills"
    attack_errors = "attack_errors"
    block_total = "block_total"
    block_kills = "block_kills"
    dig_total = "dig_total"


class StatEvidenceEventOut(BaseModel):
    action_id: str
    rally_id: str
    set_index: int = Field(ge=0)
    rally_index_in_set: int = Field(ge=0)
    action_type: ActionType
    actor_team_id: str
    video_t_start: float = Field(ge=0)
    video_t_end: float = Field(ge=0)
    court_x: float = Field(ge=0, le=1)
    court_y: float = Field(ge=0, le=1)
    quality_rating: int | None
    outcome: ActionOutcome | None


class StatEvidenceOut(BaseModel):
    formula_version: str
    category: StatCategory
    team_id: str
    zone: Zone | None
    total_events: int = Field(ge=0)
    returned_events: int = Field(ge=0)
    is_truncated: bool
    events: list[StatEvidenceEventOut]


# ---------------------------------------------------------------------------
# Video ingest (Phase 4 -- see docs/architecture/DATA_FLOW.md's upload
# lifecycle and services/api/src/volley_api/api/routes/videos.py)
# ---------------------------------------------------------------------------


class VideoStatusOut(StrEnum):
    uploaded = "uploaded"
    validating = "validating"
    ready = "ready"
    failed = "failed"


# A client-supplied content_type is echoed back into the signed upload
# target and, on R2, signed directly into the presigned URL itself -- an
# unvalidated value (e.g. "text/html") is a stored-content-type vector the
# moment R2 is fronted by a public/custom domain. Independent security
# review flagged this; allowlist to real video MIME types only. Extend
# this list deliberately, not by widening to a prefix match, if a real
# codec/container combination needs a type not covered here.
_ALLOWED_VIDEO_CONTENT_TYPES = frozenset(
    {
        "video/mp4",
        "video/quicktime",
        "video/x-matroska",
        "video/webm",
        "video/x-msvideo",
        "video/mpeg",
        "video/mp2t",
        "video/ogg",
        "application/octet-stream",  # some browsers/OSes send this for video files
    }
)


class VideoUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=100)
    match_id: str | None = None
    size_bytes: int | None = Field(default=None, gt=0)

    @field_validator("content_type")
    @classmethod
    def _content_type_must_be_video(cls, value: str) -> str:
        normalized = value.split(";", 1)[0].strip().lower()
        if normalized not in _ALLOWED_VIDEO_CONTENT_TYPES:
            raise ValueError(
                f"content_type {value!r} is not an allowed video type "
                f"(allowed: {sorted(_ALLOWED_VIDEO_CONTENT_TYPES)})"
            )
        return value


class UploadTargetOut(BaseModel):
    """Shape of a signed-upload target -- mirrors what a real S3/R2
    presigned PUT looks like (url + method + headers the client must send)
    so the local-dev and production code paths present an identical
    contract to the browser. See volley_storage.base.UploadTarget."""

    url: str
    method: Literal["PUT"]
    headers: dict[str, str]
    expires_at: datetime


class VideoUploadResponse(BaseModel):
    video_id: str
    upload: UploadTargetOut


class DownloadTargetOut(BaseModel):
    """Shape of a signed-download target -- mirrors what a real S3/R2
    presigned GET looks like (just a url + expiry; unlike upload there's
    no method/headers the client must set, a <video> element's `src` or a
    plain `fetch` both just GET the url directly). See
    volley_storage.base.DownloadTarget."""

    url: str
    expires_at: datetime


class VideoPlaybackResponse(BaseModel):
    video_id: str
    playback: DownloadTargetOut


class PipelineRunStatusOut(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class DetectionBoxOut(BaseModel):
    """One box within a `VideoDetectionFrameOut`'s `detections` list --
    deliberately a small projection of `PlayerTrackPreannotation` (see
    volley_domain.preannotation), not the full model: the frontend overlay
    only ever needs bbox/confidence/outlier flag, and re-declaring the full
    provenance/review-audit shape here would let a client mistake this
    exploratory overlay for a reviewable CVAT preannotation, which it is
    not (nothing here is queued for human review)."""

    candidate_id: str
    bbox: dict[str, float]
    confidence: float = Field(ge=0, le=1)
    jersey_color_outlier: bool = False


class BallDetectionBoxOut(BaseModel):
    """One ball box within a `VideoDetectionFrameOut`'s `balls` list -- a
    single-frame observed pixel position only (RF-DETR's COCO "sports
    ball" class), never a trajectory point. Deliberately has no
    `temporal_source`/velocity/court-plane fields: those require a working
    court-calibration pipeline this project doesn't have yet for real
    video (CLAUDE.md's fixed Ball decision -- "never a normal detector
    class... never present interpolation as observation"). Any smoothing
    between two of these real observed points (e.g. for playback) happens
    client-side at render time and is never persisted as a new observation.

    `is_static_false_positive` is set by a post-run pass
    (volley_worker.ball_filtering) when this exact screen position recurs
    across a span of many seconds -- found empirically against real
    footage to be the signature of a fixed scene object (a court logo, an
    ad board), not the real ball, which is never stationary that long
    during active play. Never deletes the underlying detection -- see that
    module's docstring for why this stays a flag, not a filter applied
    before storage."""

    candidate_id: str
    bbox: dict[str, float]
    confidence: float = Field(ge=0, le=1)
    is_static_false_positive: bool = False


class VideoDetectionFrameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    frame_index: int
    timestamp_seconds: float
    detections: list[DetectionBoxOut]
    balls: list[BallDetectionBoxOut]


class VideoDetectionStatusOut(BaseModel):
    """Polled by the frontend after `POST /videos/{id}/detect`. `status` is
    None when no detection run has ever been triggered for this video --
    the frontend must render an honest "not analyzed yet" state, never a
    fabricated empty result, per CLAUDE.md's abstention principle.

    `frames_total` is None until the worker has finished frame extraction
    (it needs the real sampled-frame count, not an estimate) -- a client
    showing a progress bar should treat "status running, frames_total still
    None" as "extracting frames," not divide by zero."""

    pipeline_run_id: str | None
    status: PipelineRunStatusOut | None
    model_version: str | None
    sample_fps: float | None
    frames_detected: int
    frames_total: int | None
    error: str | None


class TriggerDetectionRequest(BaseModel):
    """Optional body for `POST /videos/{id}/detect`. `start_offset_seconds`
    skips the video's own first N seconds -- lets a caller skip real
    warmup/pre-play footage and start analysis from the moment play
    actually begins. `max_duration_seconds` caps extraction to N seconds
    *from that starting point* -- lets a caller deliberately preview/test
    against a short prefix instead of committing CPU-only local inference
    to the whole remaining runtime up front. `sample_fps` overrides the
    worker's env-configured default detection rate for this one run --
    lets a caller pay for a much denser ball-motion sample on a short,
    deliberately scoped window (paired with the two fields above) without
    redeploying the worker for every run."""

    max_duration_seconds: float | None = Field(default=None, gt=0)
    start_offset_seconds: float | None = Field(default=None, ge=0)
    sample_fps: float | None = Field(default=None, gt=0)


class TriggerDetectionResponse(BaseModel):
    pipeline_run_id: str
    status: PipelineRunStatusOut


class HomographyMethodOut(StrEnum):
    automatic = "automatic"
    manual = "manual"
    hybrid = "hybrid"


class ShotTypeOut(StrEnum):
    main_wide = "main_wide"
    endline_wide = "endline_wide"
    side_wide = "side_wide"
    closeup = "closeup"
    replay = "replay"
    scoreboard = "scoreboard"
    other = "other"


class TacticalUsabilityOut(StrEnum):
    usable = "usable"
    not_usable = "not_usable"
    partial = "partial"


class CourtKeypointIn(BaseModel):
    """One clicked (or explicitly marked-occluded) point from the manual
    calibration UI. `keypoint_name` must be one of the 10 named
    intersections `volley_domain.annotation.COURT_KEYPOINT_NAMES` already
    fixes -- see that module and docs/datasets/PROFESSIONAL_ANNOTATION_PROTOCOL.md's
    "Court calibration marks" section for the convention this mirrors."""

    keypoint_name: str
    x_pixel: float = Field(ge=0)
    y_pixel: float = Field(ge=0)
    visible: bool = True


class CreateCourtCalibrationRequest(BaseModel):
    """Body for `POST /videos/{id}/court-calibration`. Manual calibration
    only (CLAUDE.md's fixed Court decision: "a correct manual calibration
    beats a false automatic one") -- no auto-detection path exists yet.
    `image_width`/`image_height` must be the exact native pixel frame the
    keypoints were clicked against (a homography fitted on one frame size
    is silently wrong by a constant scale factor if applied to another).
    `net_height_m` is optional and display-only -- see CourtCalibration's
    own docstring for why it is never used to compute ball height/net
    clearance."""

    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    keypoints: list[CourtKeypointIn] = Field(min_length=4)
    net_height_m: float | None = Field(default=None, gt=0)
    court_width_m: float = Field(default=9.0, gt=0)
    court_length_m: float = Field(default=18.0, gt=0)
    camera_shot_type: ShotTypeOut = ShotTypeOut.main_wide
    camera_tactical_usable: TacticalUsabilityOut = TacticalUsabilityOut.usable
    # Whether the near side's zone 1 (serve position) is on the left or
    # right as viewed in the frame -- optional, since a calibration is
    # still fully valid for side/front-back-row without it (see
    # CourtCalibration's own docstring on why this is never guessed).
    zone_mirror_x: bool | None = Field(default=None)

    @model_validator(mode="after")
    def _at_least_four_visible_named_keypoints(self) -> CreateCourtCalibrationRequest:
        visible = [k for k in self.keypoints if k.visible]
        if len(visible) < 4:
            raise ValueError("at least 4 visible, named keypoints are required")
        unknown = {k.keypoint_name for k in visible} - set(COURT_KEYPOINT_NAMES)
        if unknown:
            raise ValueError(f"unknown keypoint names: {sorted(unknown)}")
        return self


class CourtCalibrationPreviewRequest(BaseModel):
    """Body for `POST /videos/{id}/court-calibration/preview` -- the same
    keypoint shape as `CreateCourtCalibrationRequest`, minus the fields
    that don't affect reprojection error, so a live-typing UI can debounce
    a cheap preview call without persisting anything."""

    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    keypoints: list[CourtKeypointIn] = Field(min_length=4)

    @model_validator(mode="after")
    def _at_least_four_visible_named_keypoints(self) -> CourtCalibrationPreviewRequest:
        visible = [k for k in self.keypoints if k.visible]
        if len(visible) < 4:
            raise ValueError("at least 4 visible, named keypoints are required")
        unknown = {k.keypoint_name for k in visible} - set(COURT_KEYPOINT_NAMES)
        if unknown:
            raise ValueError(f"unknown keypoint names: {sorted(unknown)}")
        return self


class CourtCalibrationPreviewResponse(BaseModel):
    reprojection_error_px: float


class CourtCalibrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    camera_segment_id: str
    method: HomographyMethodOut
    image_width: int
    image_height: int
    homography_matrix: list[float]
    keypoints: list[dict] | None
    net_height_m: float | None
    court_width_m: float
    court_length_m: float
    zone_mirror_x: bool | None
    reprojection_error_px: float | None
    confidence: float | None
    created_by_user_id: str | None
    created_at: datetime


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    match_id: str | None
    filename: str
    duration_seconds: float | None
    fps: float | None
    codec: str | None
    video_hash: str | None
    uploaded_by_user_id: str
    uploaded_at: datetime
    status: VideoStatusOut
    error: str | None
