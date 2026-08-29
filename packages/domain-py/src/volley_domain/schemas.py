"""Pydantic v2 schemas: the API contract. FastAPI's OpenAPI spec is generated
directly from these -- see packages/contracts, which turns that spec into
TypeScript types/client. Never hand-duplicate these shapes in TypeScript.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class MatchStatisticsOut(BaseModel):
    """API-facing wrapper for volley_domain.stats.engine.MatchStatistics --
    kept as a permissive dict-of-dicts shape here rather than re-declaring
    every stats dataclass as a Pydantic model; the engine's dataclasses are
    the source of truth for the *shape*, this is just what crosses the
    OpenAPI boundary. Revisit if a stronger contract is needed once the
    frontend (Phase 3) is actually consuming this."""

    formula_version: str
    serve: dict
    reception: dict
    attack: dict
    block: dict
    dig: dict
    sideout_breakpoint: dict
    setter_distribution: dict
    rally_duration: dict
