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
    Boolean,
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
    INGEST = "ingest"  # ffprobe/ffmpeg container/codec/PTS extraction, not a trained model
    COURT_CALIBRATION = "court_calibration"
    DETECTION = "detection"
    TRACKING = "tracking"
    POSE = "pose"
    BALL_TRAJECTORY = "ball_trajectory"
    CONTACT_DETECTION = "contact_detection"
    ACTION_RECOGNITION = "action_recognition"
    BIOMECHANICS = "biomechanics"
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
    # Added 2026-08-31 alongside CameraSegment/CourtCalibration/BlockAttempt
    # (independent architecture review) -- `block_mode` is, by the
    # protocol's own admission, the most subjective field this project
    # records ("do not guess"), and a manual recalibration superseding an
    # automatic one is the textbook human correction; neither had a legal
    # correction target before this.
    CAMERA_SEGMENT = "camera_segment"
    COURT_CALIBRATION = "court_calibration"
    BLOCK_ATTEMPT = "block_attempt"


class ShotType(enum.StrEnum):
    """What a CameraSegment's framing actually shows -- see
    PROFESSIONAL_ANNOTATION_PROTOCOL.md's "Court calibration marks"
    section. REPLAY/CLOSEUP/SCOREBOARD segments carry
    tactical_usable=NOT_USABLE so they can never silently enter real-match
    statistics alongside genuine live-play framing."""

    MAIN_WIDE = "main_wide"
    ENDLINE_WIDE = "endline_wide"
    SIDE_WIDE = "side_wide"
    CLOSEUP = "closeup"
    REPLAY = "replay"
    SCOREBOARD = "scoreboard"
    OTHER = "other"


class TacticalUsability(enum.StrEnum):
    USABLE = "usable"
    NOT_USABLE = "not_usable"
    PARTIAL = "partial"


class HomographyMethod(enum.StrEnum):
    """Deliberately the same three values as
    `volley_domain.annotation.CameraCalibrationAnnotation.calibration_mode`
    (`automatic`/`manual`/`hybrid`) -- CLAUDE.md's own fixed Court decision
    wording is "hybrid auto-calibration ... with a manual ... fallback",
    and the ground-truth annotation schema already uses exactly this
    vocabulary. An earlier draft of this enum used
    auto_lines_keypoints/manual_four_point/manual_eight_point instead,
    which had no `hybrid` value at all and didn't line up with the
    existing annotation schema -- caught by independent architecture
    review. The four/eight-point distinction isn't lost: it's derivable
    from `len(CourtCalibration.keypoints)`, not a separate enum axis."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"
    HYBRID = "hybrid"


class BlockMode(enum.StrEnum):
    """FIVB's read-block vs. commit-block tactical distinction -- see
    BlockAttempt. UNKNOWN is the required default: a scout should never
    mark COMMIT just because a blocker moved early if intent can't
    reasonably be determined from the footage (see
    PROFESSIONAL_ANNOTATION_PROTOCOL.md)."""

    READ = "read"
    COMMIT = "commit"
    SWING = "swing"
    UNKNOWN = "unknown"


class BlockRole(enum.StrEnum):
    SOLO = "solo"
    LEFT = "left"
    MIDDLE = "middle"
    RIGHT = "right"
    ASSIST = "assist"
    UNKNOWN = "unknown"


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


class BlockAttempt(Base):
    """A blocker's tactical participation in a block, whether or not they
    actually touched the ball -- deliberately separate from
    Action(action_type=BLOCK), which only exists when a real ball contact
    happened. Without this table, a blocker who jumped and committed to
    the block but never touched the ball has nowhere to be recorded at
    all -- roughly half of real defensive block information (per the
    external annotation-spec review this entity is a direct response to).
    When the blocker DID touch the ball, both rows exist for the same
    event: this one for the tactical participation (jump, role, read vs.
    commit), an Action(action_type=BLOCK) for the contact itself -- linked
    via `action_id` when applicable. `block_count`/seam width/distance-to-
    attacker are deliberately NOT columns here -- they derive from
    multiple BlockAttempt rows plus PlayerObservation positions, matching
    this project's "annotate the fact, derive the feature" rule (see
    docs/domain/ONTOLOGY.md).

    `model_run_id` is NOT NULL/CASCADE and `confidence` is NOT NULL --
    same reasoning as `Action`'s own fields (see that class's docstring):
    `BlockAttempt` only carries a bare `video_t` float, and reaches a
    Video only via `Rally -> MatchSet -> Match`, which is nullable and can
    have more than one Video. A nullable/SET-NULL `model_run_id` would
    make it impossible to resolve which video `video_t` even refers to,
    and would leave ghost rows behind (with both FKs nulled) after their
    originating ModelRun -- and the Actions it produced -- are deleted. An
    earlier draft left both nullable, exactly the mistake `Action`'s own
    docstring already warns against; caught by independent architecture
    review before any real row existed to migrate."""

    __tablename__ = "block_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rally_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rallies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    actor_roster_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rosters.id", ondelete="SET NULL"), nullable=True
    )
    actor_team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    video_t: Mapped[float] = mapped_column(Float, nullable=False)
    # Acting team's own attacking frame, unmirrored -- same convention as
    # Action.court_x/court_y (see ActionRecord's docstring in stats/records.py).
    court_x: Mapped[float] = mapped_column(Float, nullable=False)
    court_y: Mapped[float] = mapped_column(Float, nullable=False)
    block_mode: Mapped[BlockMode] = mapped_column(
        Enum(BlockMode, native_enum=False, length=16), default=BlockMode.UNKNOWN, nullable=False
    )
    block_role: Mapped[BlockRole] = mapped_column(
        Enum(BlockRole, native_enum=False, length=16), default=BlockRole.UNKNOWN, nullable=False
    )
    jumped: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Set only when this blocker also actually touched the ball -- see
    # this class's own docstring.
    action_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("actions.id", ondelete="SET NULL"), nullable=True
    )
    model_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
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
    # Nullable (Phase 4 change, migration 0003): the API creates this row at
    # upload-URL-issuance time, before the bytes exist anywhere to hash --
    # video_hash is only knowable once the worker has streamed the full
    # object and computed SHA-256 over it (see DATA_FLOW.md's upload
    # lifecycle: browser -> storage -> worker computes hash). A NOT NULL
    # constraint here would force either a fake placeholder hash (which
    # would misrepresent an un-hashed video as content-addressed, violating
    # the same "never fabricate a number" principle as everywhere else in
    # this project) or delaying row creation until after ingest, which loses
    # the ability to give the client a stable video_id to poll before the
    # upload even completes. The org-scoped uniqueness constraint below
    # still applies once a hash exists; two concurrent in-flight (not yet
    # hashed) uploads never collide on this column because SQL UNIQUE
    # constraints don't consider NULL values equal to each other.
    video_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # PTS mapping + frame geometry (Phase 4 change, migration 0004) --
    # DATA_FLOW.md's "Video identity" section requires this: "never key
    # anything by frame number alone: every frame reference carries
    # original PTS/time ... and the mapping between them." An earlier
    # version of the ingest pipeline stored only `fps` (avg_frame_rate) and
    # computed every ground-truth timestamp downstream as
    # `frame_index / fps` -- wrong for any variable-frame-rate source, and
    # silently offset for any container with non-zero start_time (e.g.
    # MPEG-TS, common from fixed-camera gym recorders). Caught by
    # independent architecture review before any real annotation existed
    # to be invalidated by it.
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    # ffprobe's own time_base string (e.g. "1/90000") for the probed video
    # stream -- kept as the raw fraction rather than converted to a float,
    # since PTS values are only exact when interpreted against this exact
    # rational, not a lossy decimal approximation of it.
    time_base: Mapped[str | None] = mapped_column(String(32), nullable=True)
    uploaded_by_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, native_enum=False, length=16),
        default=VideoStatus.UPLOADED,
        nullable=False,
    )
    # Populated only when status == FAILED (ffprobe failure, corrupt
    # container, storage read error, duplicate-hash conflict, etc.) -- see
    # services/worker/src/volley_worker/ingest.py. Mirrors ProcessingJob.error's
    # existing shape/purpose for the Phase 1 demo-processing path.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


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


class CameraSegment(Base):
    """A contiguous span of one Video where a single camera framing holds
    -- a broadcast cut/pan/zoom starts a new segment, since a single
    CourtCalibration homography is only ever valid within one camera
    framing. Formalizes CLAUDE.md's fixed Court decision ("hybrid auto-
    calibration ... with confidence, and a manual 4-8 point fallback") as
    real data, and PROFESSIONAL_ANNOTATION_PROTOCOL.md's requirement to
    "annotate the ten named intersections whenever the camera moves or a
    new clip begins." REPLAY/CLOSEUP/SCOREBOARD segments carry
    `tactical_usable=NOT_USABLE` so they can never silently enter real-
    match statistics alongside genuine live-play framing -- added in
    direct response to an external annotation-spec review that named this
    exact gap (this project's own Video/PipelineRun tables had no way to
    represent "this footage span isn't real gameplay" before now)."""

    __tablename__ = "camera_segments"
    __table_args__ = (
        UniqueConstraint("video_id", "index_in_video", name="uq_camera_segment_video_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), index=True, nullable=False
    )
    index_in_video: Mapped[int] = mapped_column(Integer, nullable=False)
    video_t_start: Mapped[float] = mapped_column(Float, nullable=False)
    video_t_end: Mapped[float | None] = mapped_column(Float, nullable=True)
    shot_type: Mapped[ShotType] = mapped_column(
        Enum(ShotType, native_enum=False, length=16), nullable=False
    )
    tactical_usable: Mapped[TacticalUsability] = mapped_column(
        Enum(TacticalUsability, native_enum=False, length=12), nullable=False
    )
    model_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("model_runs.id", ondelete="SET NULL"), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


class CourtCalibration(Base):
    """The *production* (PipelineRun-produced) counterpart of
    `volley_domain.annotation.CameraCalibrationAnnotation` (the CVAT
    ground-truth calibration schema, evaluated against by
    `dataset_factory.professional_signal_qa`) -- same relationship as
    `Action` (production, this file) vs. `ActionAnnotation` (ground
    truth, annotation.py) elsewhere in this ontology. Deliberately kept
    field-name- and shape-compatible with `CameraCalibrationAnnotation`
    rather than inventing a parallel vocabulary: an earlier draft used a
    flat, unvalidated `homography_matrix`, had no `image_width`/
    `image_height` (a homography is only valid for the pixel frame it was
    fitted on -- applying one fitted on a downscaled proxy to full-
    resolution detections is silently wrong by a constant scale factor),
    no Phase-B metric-3D fields (`camera_matrix`/`rotation_world_to_camera`/
    `translation_world_to_camera_m`/`supports_metric_3d`) that
    `professional_signal_qa` already reads from the ground-truth side, and
    a `method` enum with no `hybrid` value even though that's CLAUDE.md's
    own fixed wording for the Court decision. Caught by independent
    architecture review before any real row existed to migrate.

    `homography_matrix`/`camera_matrix`/`rotation_world_to_camera` are 3x3
    row-major matrices (9 floats each); `translation_world_to_camera_m` is
    3 floats -- all stored as JSON since they're always read/written as
    one unit and never queried column-by-column, matching
    docs/domain/ONTOLOGY.md's "CourtPosition is a value type, not a table"
    precedent. `keypoints` (also JSON, same reasoning) holds the named
    court-line/corner keypoints used to compute the homography, in
    `volley_domain.annotation.CourtKeypointAnnotation`'s own field names
    and boolean polarity -- an earlier draft used different names
    (`kp_name`/`pixel_x`/`pixel_y`) *and inverted polarity*
    (`occluded: bool` where the annotation schema uses `visible: bool`),
    which would silently invert any code copying that flag across the two
    schemas. Correct shape: `[{"keypoint_name": "sideline_near_left",
    "x_pixel": ..., "y_pixel": ..., "visible": bool}, ...]`.

    `net_height_m`/`court_width_m`/`court_length_m` were added 2026-09-01,
    closing a real gap the field-compatibility claim above had never
    actually covered: `CameraCalibrationAnnotation` has always required
    `net_height_m` and defaulted `court_width_m`/`court_length_m` (9.0/18.0),
    but this table had none of the three until a real manual-calibration
    producer needed to persist them. `net_height_m` stays nullable -- a
    calibration's homography is valid without it, and a missing value must
    never silently become a fabricated FIVB-standard default (2.43m/2.24m);
    it is display-only metadata for this pass (see
    `volley_ml.court.keypoints` and the `/court-calibration` route) and is
    never used to compute ball height or net clearance, which would need
    real vertical (Z) data a single 2D homography cannot recover.

    A CameraSegment may accumulate more than one CourtCalibration row over
    time (e.g. a manual recalibration superseding an earlier automatic
    one) -- superseded rows are never deleted, only marked via
    `superseded_at` (null means "still current"; an earlier draft relied
    on "most recent `created_at` wins" instead, which is genuinely
    ambiguous for two calibrations written in the same transaction, since
    Postgres `now()` is transaction-scoped and returns the identical
    timestamp for both -- verified directly, not assumed). `created_by_user_id`
    is set only for a manual/hybrid calibration a human produced; null for
    a fully automatic one."""

    __tablename__ = "court_calibrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    camera_segment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("camera_segments.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    method: Mapped[HomographyMethod] = mapped_column(
        Enum(HomographyMethod, native_enum=False, length=24), nullable=False
    )
    image_width: Mapped[int] = mapped_column(Integer, nullable=False)
    image_height: Mapped[int] = mapped_column(Integer, nullable=False)
    homography_matrix: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    keypoints: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    camera_matrix: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    rotation_world_to_camera: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    translation_world_to_camera_m: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    supports_metric_3d: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    net_height_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    court_width_m: Mapped[float] = mapped_column(Float, nullable=False, default=9.0)
    court_length_m: Mapped[float] = mapped_column(Float, nullable=False, default=18.0)
    # Whether the near side's zone 1 (right-back, the serve position) is
    # on the left or right as viewed in the calibrated frame -- resolves
    # ml/court/rotation.py's `mirror_x` parameter, which its own docstring
    # says "must be verified per camera setup against a frame with a known
    # server position, never guessed." Nullable: a calibration is fully
    # valid for side (near/far) and front/back-row without it -- only the
    # exact numbered zone (1-6) needs it, and stays unavailable, not
    # guessed, until a human sets it.
    zone_mirror_x: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reprojection_error_px: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("model_runs.id", ondelete="SET NULL"), nullable=True
    )
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
    # Populated only when status=FAILED -- mirrors ProcessingJob.error
    # (models.py). A failed run must explain why without a human having to
    # dig through worker logs; a retry creates a *new* PipelineRun row
    # rather than mutating this one (see this class's own docstring: "one
    # execution", not a mutable job-progress record like ProcessingJob).
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


class ModelRun(Base):
    """One stage of a PipelineRun. `Action` and `BlockAttempt` link here
    with a required (NOT NULL/CASCADE) `model_run_id` -- both are, by this
    ontology's own "no generic Prediction table" decision, themselves
    predictions, so they must always carry full provenance.
    `BallObservation`/`PlayerObservation` do the same. `CameraSegment`/
    `CourtCalibration` link here too but with a *nullable* `model_run_id`
    (SET NULL) -- unlike a prediction about a specific rally/player event,
    a manual/hybrid calibration can legitimately have no single model run
    behind it, the same reasoning `Rally`/`Phase` already use for their
    own nullable `model_run_id`. This is the chain that answers "why does
    the product show me this" (model_version, weights_hash,
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


class RallyAnalysisResult(Base):
    """Immutable, animation-ready output for one Rally and PipelineRun.

    Raw observations and Actions remain normalized in their own tables for
    querying and statistics. This versioned bundle is the exact, internally
    consistent snapshot consumed by replay/biomechanics clients: frame PTS,
    player poses, ball trajectory, contacts, uncertainties and capability
    abstentions must all come from the same pipeline execution.

    ``organization_id`` and ``match_id`` are deliberately denormalized. They
    make the security boundary explicit and cheap to enforce on every API
    read; persistence validates them against Video/Rally/PipelineRun before
    inserting the row, so they are never accepted as untrusted duplicates.
    """

    __tablename__ = "rally_analysis_results"
    __table_args__ = (
        UniqueConstraint(
            "rally_id",
            "pipeline_run_id",
            "schema_version",
            name="uq_rally_analysis_pipeline_schema",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    match_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("matches.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rally_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rallies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), index=True, nullable=False
    )
    pipeline_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    bundle_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


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


class VideoDetectionFrame(Base):
    """Exploratory, non-ground-truth person-box detections for one sampled
    frame of a real uploaded Video, produced by RF-DETR nano (COCO-
    pretrained -- see TECH_DEBT.md for why no volleyball-specific weights
    exist yet). Deliberately distinct from `PlayerObservation`: that table
    requires calibrated `court_x`/`court_y`, which no real uploaded video
    has (no working homography pipeline is wired to real footage yet) --
    forcing raw detections into that table would mean fabricating court
    coordinates, exactly what CLAUDE.md's "abstain rather than fabricate"
    principle forbids. This table stores only image-space boxes, the same
    `PlayerTrackPreannotation` shape (see volley_domain.preannotation)
    already produced by `ml/detection/rfdetr_preannotation.py` for the
    CVAT pipeline -- the same adapter code produces both, just pointed at
    real-video frames instead of golden-set dataset frames.

    CPU-only local inference (no cloud GPU spend -- see ROADMAP.md/
    ml/execution/gpu_executor.py) is far too slow to run every frame of a
    full match, so frames are sampled at a fixed low rate: `sample_fps`
    records what rate this row's `frame_index`/`timestamp_seconds` actually
    came from, so a client can correctly space/interpolate between rows
    rather than assuming per-frame density.

    One row per sampled frame (not one row per detected box) -- `detections`
    holds the full list of that frame's `PlayerTrackPreannotation`-shaped
    dicts as JSON, and `ball_detections` the same frame's ball boxes (added
    2026-08-31). There is no per-box query need here (unlike
    BallObservation/PlayerObservation, which are queried per-observation
    for tracking/statistics); a client always wants "everything detected
    near this timestamp" as one unit, exactly what a JSON blob per frame
    gives it without a join.
    """

    __tablename__ = "video_detection_frames"
    __table_args__ = (
        UniqueConstraint("model_run_id", "frame_index", name="uq_detection_frame_run_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("model_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_seconds: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    detections: Mapped[list] = mapped_column(JSON, nullable=False)
    # Exploratory ball-box detections for this same sampled frame -- RF-DETR
    # nano's COCO "sports ball" class (id 37), never fused into
    # BallObservation (see this class's own docstring): each entry is a
    # single-frame observed pixel position with no trajectory, velocity, or
    # court-plane projection computed, since none of that is possible
    # without a working court calibration/homography pipeline (CLAUDE.md's
    # fixed Court decision), which doesn't exist for real video yet. A
    # default of [] (not nullable) rather than a separate migration-added
    # column with a server_default keeps every row shape uniform regardless
    # of which pipeline version produced it.
    ball_detections: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
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
