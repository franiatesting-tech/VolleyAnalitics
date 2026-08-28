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
