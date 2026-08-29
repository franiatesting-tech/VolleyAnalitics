"""The full volleyball domain ontology -- see docs/domain/ONTOLOGY.md for the
entity descriptions, the design decisions behind this schema (why there's no
generic Prediction table, why CourtPosition is a value type not a table,
etc.), and the ER diagram. Read that document before extending this file.

`organization_id` columns are plain indexed strings with no FK to Better
Auth's own tables, exactly like models.py's Match -- see CLAUDE.md's auth
ownership rule.
"""

import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from volley_domain.base import Base, new_id, utcnow

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RosterPosition(enum.StrEnum):
    OH = "OH"
    OP = "OP"
    MB = "MB"
    S = "S"
    L = "L"


class ActionType(enum.StrEnum):
    SERVE = "serve"
    RECEPTION = "reception"
    SET = "set"
    ATTACK = "attack"
    TIP = "tip"
    BLOCK = "block"
    DIG = "dig"
    FREE_BALL = "free_ball"
    TRANSITION = "transition"


class OutcomeResult(enum.StrEnum):
    CONTINUE = "continue"
    POINT = "point"
    ERROR = "error"


class PhaseType(enum.StrEnum):
    SERVE = "serve"
    RECEPTION = "reception"
    TRANSITION = "transition"


class ReviewedStatus(enum.StrEnum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"


class ReviewStatus(enum.StrEnum):
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class BallProvenance(enum.StrEnum):
    OBSERVED = "observed"
    INTERPOLATED = "interpolated"
    PREDICTED = "predicted"


class VideoStatus(enum.StrEnum):
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    READY = "ready"
    FAILED = "failed"


class VideoAssetKind(enum.StrEnum):
    ORIGINAL = "original"
    PROXY = "proxy"
    CLIP = "clip"


class PipelineRunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ModelRunStage(enum.StrEnum):
    DETECTION = "detection"
    TRACKING = "tracking"
    POSE = "pose"
    ACTION_RECOGNITION = "action_recognition"
    SYNTHETIC = "synthetic"  # Phase 1/2's stand-in generator, not a real CV stage


class CorrectionTargetType(enum.StrEnum):
    """What a HumanCorrection/ReviewedLabel's target_id refers to. Kept as an
    explicit enum (not a free string) so a typo can't silently create an
    orphaned correction that nothing ever queries back out."""

    ACTION = "action"
    OUTCOME = "outcome"
    BALL_OBSERVATION = "ball_observation"
    PLAYER_OBSERVATION = "player_observation"
    RALLY = "rally"


# ---------------------------------------------------------------------------
# Roster / competition structure
# ---------------------------------------------------------------------------


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


class Roster(Base):
    """A Player's membership on a Team for a Season, with the season-specific
    facts (jersey number, primary position) that don't belong on Player
    itself. Everything downstream (Lineup, Rotation, Action.actor_roster_id)
    references Roster, never Player directly -- see ONTOLOGY.md."""

    __tablename__ = "rosters"
    __table_args__ = (
        UniqueConstraint(
            "team_id", "season_id", "jersey_number", name="uq_roster_team_season_jersey"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), index=True, nullable=False
    )
    player_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("players.id", ondelete="CASCADE"), index=True, nullable=False
    )
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), index=True, nullable=False
    )
    jersey_number: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[RosterPosition] = mapped_column(
        Enum(RosterPosition, native_enum=False, length=8), nullable=False
    )
    is_libero: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


# ---------------------------------------------------------------------------
# Match structure
# ---------------------------------------------------------------------------


class MatchSet(Base):
    """A set within a Match. Named MatchSet (not Set) to avoid shadowing the
    Python builtin at the class-name level -- __tablename__ is still the
    natural "sets"."""

    __tablename__ = "sets"
    __table_args__ = (UniqueConstraint("match_id", "index", name="uq_set_match_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    match_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("matches.id", ondelete="CASCADE"), index=True, nullable=False
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    home_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    away_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    winner_team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


class Lineup(Base):
    """Which Roster entries a team is drawing from for a MatchSet --
    personnel selection, independent of court arrangement (see Rotation)."""

    __tablename__ = "lineups"
    __table_args__ = (UniqueConstraint("set_id", "team_id", name="uq_lineup_set_team"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


class LineupPlayer(Base):
    __tablename__ = "lineup_players"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    lineup_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lineups.id", ondelete="CASCADE"), index=True, nullable=False
    )
    roster_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rosters.id", ondelete="CASCADE"), nullable=False
    )
    is_starting: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_libero_for_set: Mapped[bool] = mapped_column(default=False, nullable=False)


class Rotation(Base):
    """A snapshot of which Roster entry occupies each of the 6 court
    positions, valid from `effective_from_rally_id` onward until the next
    Rotation row for that team+set (i.e. changes on every sideout). The
    first Rotation row for a set (effective_from_rally_id = the set's first
    rally) is the starting rotation -- there is no separate "starting
    lineup arrangement" table beyond this."""

    __tablename__ = "rotations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    p1_roster_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rosters.id"), nullable=True
    )
    p2_roster_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rosters.id"), nullable=True
    )
    p3_roster_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rosters.id"), nullable=True
    )
    p4_roster_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rosters.id"), nullable=True
    )
    p5_roster_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rosters.id"), nullable=True
    )
    p6_roster_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rosters.id"), nullable=True
    )
    effective_from_rally_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rallies.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


# ---------------------------------------------------------------------------
# Rally structure
# ---------------------------------------------------------------------------


class Rally(Base):
    """Rally boundary detection is itself a model output from Phase 6
    onward (see ROADMAP.md) -- `model_run_id`/`confidence` are nullable
    (unlike Action's, see below) because a rally can also be defined by
    rule-based/manual means with no single model run to attribute it to,
    but the columns exist now so Phase 6's real detector has somewhere to
    record its provenance rather than that being an afterthought. Flagged
    by independent architecture review as a real gap in an earlier draft
    that had neither column on Rally or Phase at all."""

    __tablename__ = "rallies"
    __table_args__ = (UniqueConstraint("set_id", "index_in_set", name="uq_rally_set_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    index_in_set: Mapped[int] = mapped_column(Integer, nullable=False)
    serving_team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    point_winner_team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    video_t_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    video_t_end: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("model_runs.id", ondelete="SET NULL"), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


class Phase(Base):
    """A possession segment within a Rally (e.g. "reception," "transition
    1") -- groups Actions by which team currently has the ball, per
    ADR-001's video -> set -> rally -> phase -> action -> outcome hierarchy.
    `model_run_id`/`confidence` nullable for the same reason as Rally's."""

    __tablename__ = "phases"
    __table_args__ = (UniqueConstraint("rally_id", "index_in_rally", name="uq_phase_rally_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rally_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rallies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    index_in_rally: Mapped[int] = mapped_column(Integer, nullable=False)
    phase_type: Mapped[PhaseType] = mapped_column(
        Enum(PhaseType, native_enum=False, length=16), nullable=False
    )
    team_in_possession_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    model_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("model_runs.id", ondelete="SET NULL"), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


class Action(Base):
    """A single volleyball action -- see ONTOLOGY.md's "no generic
    Prediction table" decision: this row *is* the prediction, carrying its
    own provenance (`model_run_id`, `confidence`) rather than pointing at a
    separate wrapper. `rally_id` is denormalized from `phase_id` purely for
    query convenience (list all actions in a rally without a join through
    phases) -- `phase_id` remains the source of truth for hierarchy.

    `model_run_id` is NOT NULL with ON DELETE CASCADE -- unlike Rally/Phase
    (which can legitimately have no single model run behind them), every
    Action is, by this schema's own "no generic Prediction table" decision,
    itself a prediction, so it must always have provenance. An earlier
    draft left this nullable with SET NULL, which is exactly what CLAUDE.md's
    "every prediction must link ... model_version, weights_hash,
    dataset_version" requirement forbids -- inconsistent with
    BallObservation/PlayerObservation, which were already correctly
    non-nullable/CASCADE. Caught by independent architecture review."""

    __tablename__ = "actions"
    __table_args__ = (UniqueConstraint("phase_id", "index_in_phase", name="uq_action_phase_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    phase_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("phases.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rally_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rallies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    index_in_phase: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[ActionType] = mapped_column(
        Enum(ActionType, native_enum=False, length=16), nullable=False
    )
    actor_roster_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rosters.id", ondelete="SET NULL"), nullable=True
    )
    actor_team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    video_t_start: Mapped[float] = mapped_column(Float, nullable=False)
    video_t_end: Mapped[float] = mapped_column(Float, nullable=False)
    court_x: Mapped[float] = mapped_column(Float, nullable=False)
    court_y: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False
    )
    reviewed_status: Mapped[ReviewedStatus] = mapped_column(
        Enum(ReviewedStatus, native_enum=False, length=16),
        default=ReviewedStatus.UNREVIEWED,
        nullable=False,
    )
    # Configurable-scale quality grade (see ONTOLOGY.md "universal vs.
    # configurable") -- primarily reception rating (commonly 0-3, some
    # programs use 0-4 or letter grades mapped to ints), but generic enough
    # for other quality-graded actions (e.g. dig quality). The *scale*
    # itself is never assumed here; the statistics engine takes it as
    # config. Null when not applicable/not yet graded.
    quality_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_clip_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    # One-to-one with Outcome. uselist=False + Outcome.action_id's UNIQUE
    # constraint together enforce the 1:1 cardinality at both the Python
    # and DB level. Not eager-loaded by default -- callers that need it in
    # one round trip should use a joined query (see api/routes/ontology.py).
    outcome: Mapped["Outcome | None"] = relationship(back_populates="action", uselist=False)


class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("actions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    action: Mapped["Action"] = relationship(back_populates="outcome")
    result: Mapped[OutcomeResult] = mapped_column(
        Enum(OutcomeResult, native_enum=False, length=16), nullable=False
    )
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


# ---------------------------------------------------------------------------
# Video & pipeline provenance
# ---------------------------------------------------------------------------


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        # Scoped to organization_id, not globally unique -- two different
        # clients uploading byte-identical footage (e.g. a shared vendor
        # highlight reel) must not collide with each other's Video row.
        # An earlier draft had a bare global `unique=True` on video_hash,
        # which is a cross-tenant collision risk. Caught by independent
        # architecture review.
        UniqueConstraint("organization_id", "video_hash", name="uq_video_org_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    match_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("matches.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    codec: Mapped[str | None] = mapped_column(String(50), nullable=True)
    video_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, native_enum=False, length=16),
        default=VideoStatus.UPLOADED,
        nullable=False,
    )


class VideoAsset(Base):
    __tablename__ = "video_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[VideoAssetKind] = mapped_column(
        Enum(VideoAssetKind, native_enum=False, length=16), nullable=False
    )
    storage_ref: Mapped[str] = mapped_column(String(1000), nullable=False)
    start_ts: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_ts: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


class PipelineRun(Base):
    """One execution of the analysis pipeline against a Video -- the
    `video_hash + pipeline_version + config_hash` idempotency key from
    DATA_FLOW.md, as a real row.

    `video_id` is nullable specifically for `ModelRunStage.SYNTHETIC` runs
    (see synthetic/persistence.py): synthetic/demo data has no source video
    to reference, and a fake placeholder Video row would misrepresent it as
    if one existed. Every *real* pipeline run (any other ModelRunStage)
    must still set video_id -- this is a deliberate single exception, not a
    general relaxation, and application code must not create a non-SYNTHETIC
    PipelineRun with a null video_id."""

    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), index=True, nullable=True
    )
    pipeline_version: Mapped[str] = mapped_column(String(50), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[PipelineRunStatus] = mapped_column(
        Enum(PipelineRunStatus, native_enum=False, length=16),
        default=PipelineRunStatus.QUEUED,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    code_commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


class ModelRun(Base):
    """One stage of a PipelineRun. Every Action/Outcome/BallObservation/
    PlayerObservation links here -- this is the chain that answers "why
    does the product show me this" (model_version, weights_hash,
    dataset_version, per CLAUDE.md's required provenance fields)."""

    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    pipeline_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    stage: Mapped[ModelRunStage] = mapped_column(
        Enum(ModelRunStage, native_enum=False, length=32), nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    weights_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# ---------------------------------------------------------------------------
# Raw observations
# ---------------------------------------------------------------------------


class BallObservation(Base):
    __tablename__ = "ball_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False
    )
    video_t: Mapped[float] = mapped_column(Float, nullable=False)
    court_x: Mapped[float] = mapped_column(Float, nullable=False)
    court_y: Mapped[float] = mapped_column(Float, nullable=False)
    court_z: Mapped[float] = mapped_column(Float, nullable=False)
    provenance: Mapped[BallProvenance] = mapped_column(
        Enum(BallProvenance, native_enum=False, length=16), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


class PlayerObservation(Base):
    __tablename__ = "player_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False
    )
    video_t: Mapped[float] = mapped_column(Float, nullable=False)
    roster_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rosters.id", ondelete="SET NULL"), nullable=True
    )
    track_id: Mapped[str] = mapped_column(String(64), nullable=False)
    team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    court_x: Mapped[float] = mapped_column(Float, nullable=False)
    court_y: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


# ---------------------------------------------------------------------------
# Human review
# ---------------------------------------------------------------------------


class HumanCorrection(Base):
    """Append-only. See ONTOLOGY.md's "Correction semantics" section for the
    exact mechanism -- this row never changes after insert, and its
    `target_id`'s row (e.g. an Action) may reflect the corrected value for
    convenience of ordinary reads, but the original prediction is always
    reconstructible from this row's `previous_value` plus the target row's
    untouched `model_run_id`/`confidence`."""

    __tablename__ = "human_corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_type: Mapped[CorrectionTargetType] = mapped_column(
        Enum(CorrectionTargetType, native_enum=False, length=32), nullable=False
    )
    target_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    corrected_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    corrected_by_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    corrected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ReviewedLabel(Base):
    """A human's review verdict on a target row -- distinct from
    HumanCorrection because confirming a prediction as correct is a review
    with no correction (see ONTOLOGY.md)."""

    __tablename__ = "reviewed_labels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_type: Mapped[CorrectionTargetType] = mapped_column(
        Enum(CorrectionTargetType, native_enum=False, length=32), nullable=False
    )
    target_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    reviewed_by_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False, length=16), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
