"""Pure input records for the statistics engine (volley_domain.stats.engine).
Deliberately decoupled from the SQLAlchemy ORM (Action/Outcome/Rally rows)
so the engine can be unit-tested without a database -- see
docs/domain/ONTOLOGY.md's "Statistics engine" section. A caller (an API
route, a service) converts ORM rows into these before calling the engine.
"""

from dataclasses import dataclass

from volley_domain.schemas import ActionType


@dataclass(frozen=True)
class ActionRecord:
    """`court_x`/`court_y` are always in the *acting team's own* attacking
    frame, per docs/domain/ONTOLOGY.md's coordinate convention -- every
    team's own actions are recorded as if they were "home," never
    pre-mirrored. Mirroring (volley_domain.court.mirror_for_away) is a
    rendering concern for overlaying both teams on one shared visual frame,
    not a fact about how a single team's own stats should be computed --
    zone attribution here always uses the unmirrored `court.ZONE_ANCHORS`."""

    id: str
    rally_id: str
    sequence: int  # chronological order within the rally -- lets the engine
    # pair a "set" action with the attack that immediately follows it
    # (setter distribution) without needing phase/timestamp joins.
    action_type: ActionType
    actor_team_id: str
    actor_roster_id: str | None
    outcome: str | None  # "continue" | "point" | "error" | None (no Outcome row yet)
    court_x: float
    court_y: float
    quality_rating: int | None = None
    # Mirrors Outcome.detail -- e.g. "blocked" for an attack error caused
    # by an opposing block stuff. When present, compute_attack_stats
    # trusts it directly; when absent (older/unlabeled data), it falls
    # back to the adjacency heuristic -- see that function's docstring.
    outcome_detail: str | None = None


@dataclass(frozen=True)
class RallyRecord:
    id: str
    serving_team_id: str
    point_winner_team_id: str | None
    duration_seconds: float | None = None
