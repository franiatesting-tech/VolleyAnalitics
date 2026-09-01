"""Pure, testable statistics engine -- see docs/domain/ONTOLOGY.md's
"Statistics engine" section. Every function here takes plain data
(ActionRecord/RallyRecord, see records.py) and a config, and returns a
result carrying `FORMULA_VERSION` -- never touches a database, never
mutates its inputs, never persists its output (see ONTOLOGY.md's
"DerivedMetric is never persisted as a mutable number" principle).

Bump FORMULA_VERSION whenever a formula changes -- it's what lets a
consumer (or a future cache, if one is ever added) know two results aren't
comparable/interchangeable just because they're both "attack efficiency."
"""

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median

from volley_domain.court import Zone, nearest_zone
from volley_domain.stats.records import ActionRecord, RallyRecord

FORMULA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Configuration (see ONTOLOGY.md "universal vs. configurable")
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReceptionRatingScale:
    """Reception rating conventions vary by program -- commonly 0-3
    (coachingvb.com), sometimes 0-4 or letter grades mapped to ints. Never
    hard-code a scale in the engine; pass one in."""

    min_value: int = 0
    max_value: int = 3
    effective_threshold: float = 2.0  # avg >= this is "running an effective offense"


DEFAULT_RECEPTION_RATING_SCALE = ReceptionRatingScale()


@dataclass(frozen=True)
class StatsConfig:
    reception_rating_scale: ReceptionRatingScale = DEFAULT_RECEPTION_RATING_SCALE


DEFAULT_CONFIG = StatsConfig()


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServeStats:
    team_id: str
    total_serves: int
    aces: int
    serve_errors: int
    zone_counts: dict[Zone, int]


@dataclass(frozen=True)
class ReceptionStats:
    team_id: str
    total_receptions: int
    rated_receptions: int
    average_rating: float | None
    is_effective: bool | None


@dataclass(frozen=True)
class AttackStats:
    team_id: str
    total_attacks: int
    kills: int
    errors: int
    blocked: int
    efficiency: float | None
    zone_counts: dict[Zone, int]
    takeoff_position_counts: dict[
        str, int
    ]  # "left" | "middle" | "right" of the attacker, NOT ball landing -- see compute_attack_stats


@dataclass(frozen=True)
class BlockStats:
    team_id: str
    total_blocks: int
    block_kills: int
    block_errors: int


@dataclass(frozen=True)
class DigStats:
    team_id: str
    total_digs: int


@dataclass(frozen=True)
class SideoutBreakpointStats:
    team_id: str
    serve_rallies: int
    serve_points_won: int
    breakpoint_pct: float | None
    reception_rallies: int
    reception_points_won: int
    sideout_pct: float | None


@dataclass(frozen=True)
class SetterDistributionEntry:
    setter_roster_id: str
    total_sets: int
    followed_by_attack: int
    zone_counts: dict[Zone, int]


@dataclass(frozen=True)
class RallyDurationStats:
    count: int
    mean_seconds: float | None
    median_seconds: float | None
    min_seconds: float | None
    max_seconds: float | None


@dataclass(frozen=True)
class MatchStatistics:
    formula_version: str
    serve: dict[str, ServeStats]
    reception: dict[str, ReceptionStats]
    attack: dict[str, AttackStats]
    block: dict[str, BlockStats]
    dig: dict[str, DigStats]
    sideout_breakpoint: dict[str, SideoutBreakpointStats]
    setter_distribution: dict[str, SetterDistributionEntry]
    rally_duration: RallyDurationStats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _team_ids(actions: list[ActionRecord], rallies: list[RallyRecord]) -> set[str]:
    ids = {a.actor_team_id for a in actions}
    ids |= {r.serving_team_id for r in rallies}
    ids |= {r.point_winner_team_id for r in rallies if r.point_winner_team_id}
    return ids


def _safe_div(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator > 0 else None


# ---------------------------------------------------------------------------
# Serve
# ---------------------------------------------------------------------------


def compute_serve_stats(actions: list[ActionRecord]) -> dict[str, ServeStats]:
    """Aces: a serve whose Outcome is "point" (unreturnable/direct point).
    Serve errors: a serve whose Outcome is "error" (net/out/foot fault)."""
    by_team: dict[str, list[ActionRecord]] = defaultdict(list)
    for a in actions:
        if a.action_type == "serve":
            by_team[a.actor_team_id].append(a)

    result: dict[str, ServeStats] = {}
    for team_id, serves in by_team.items():
        zone_counts: dict[Zone, int] = defaultdict(int)
        aces = errors = 0
        for s in serves:
            zone_counts[nearest_zone(s.court_x, s.court_y, "home")] += 1
            if s.outcome == "point":
                aces += 1
            elif s.outcome == "error":
                errors += 1
        result[team_id] = ServeStats(
            team_id=team_id,
            total_serves=len(serves),
            aces=aces,
            serve_errors=errors,
            zone_counts=dict(zone_counts),
        )
    return result


# ---------------------------------------------------------------------------
# Reception
# ---------------------------------------------------------------------------


def compute_reception_stats(
    actions: list[ActionRecord], config: StatsConfig = DEFAULT_CONFIG
) -> dict[str, ReceptionStats]:
    by_team: dict[str, list[ActionRecord]] = defaultdict(list)
    for a in actions:
        if a.action_type == "reception":
            by_team[a.actor_team_id].append(a)

    result: dict[str, ReceptionStats] = {}
    for team_id, receptions in by_team.items():
        rated = [r.quality_rating for r in receptions if r.quality_rating is not None]
        avg = mean(rated) if rated else None
        result[team_id] = ReceptionStats(
            team_id=team_id,
            total_receptions=len(receptions),
            rated_receptions=len(rated),
            average_rating=avg,
            is_effective=(avg >= config.reception_rating_scale.effective_threshold)
            if avg is not None
            else None,
        )
    return result


# ---------------------------------------------------------------------------
# Attack
# ---------------------------------------------------------------------------


_ATTACK_LIKE_ACTION_TYPES = ("attack", "tip")


def _takeoff_position_bucket(court_x: float) -> str:
    """Coarse left/middle/right split of the same (x, y) an attack Action
    already carries -- i.e. where the *attacker* was standing, not where
    the ball landed. Deliberately NOT called "direction": to a coach,
    "attack direction" unambiguously means shot placement (line vs.
    cross-court, or a target zone on the opponent's court), which this does
    not measure and which doesn't exist as a distinct observation until a
    real CV pipeline tracks ball landing spots separately (Phase 5+) --
    an earlier version of this function mislabeled this exact bucketing as
    "direction," which an independent domain review flagged as actively
    misleading, not just imprecise. Also redundant with `zone_counts` today
    (both derived from the same coordinate) until ball-landing data exists
    to make this a genuinely different signal."""
    if court_x < 1 / 3:
        return "left"
    if court_x > 2 / 3:
        return "right"
    return "middle"


def compute_attack_stats(actions: list[ActionRecord]) -> dict[str, AttackStats]:
    """Kill: attack/tip Outcome "point". Error: Outcome "error". `tip` is
    included alongside `attack` throughout -- a tip is a shot-selection
    variant of an attack in standard scorekeeping (DataVolley, NCAA/SDHSAA
    worksheets), not a separate statistical category; an earlier version
    filtered on `action_type == "attack"` only, silently dropping every tip
    kill/error from these stats entirely, caught by independent domain
    review rather than any test.

    Blocked: an attack error specifically caused by an opposing block
    stuff. Primary signal is `ActionRecord.outcome_detail == "blocked"`
    (mirrors `Outcome.detail`, set directly by whatever labels the action
    -- the synthetic generator now produces real blocked-attack sequences
    this way, see generator.py's last-exchange block-kill branch). Falls
    back to the original adjacency heuristic (an error immediately
    followed by an opposing "block" action) only when `outcome_detail` is
    unset, so older/unlabeled data (or a future annotator/model that
    hasn't started setting `detail` yet) still gets a best-effort count
    instead of silently reading 0. Fixed 2026-08-30 (TECH_DEBT.md) -- the
    heuristic-only version was flagged by independent domain review as
    real but never exercised, since the generator never produced the
    adjacency pattern it depended on.

    Efficiency: (kills - errors) / total_attempts, verified against
    SDHSAA/NCAA convention -- see docs/domain/ONTOLOGY.md."""
    by_team: dict[str, list[ActionRecord]] = defaultdict(list)
    for a in actions:
        if a.action_type in _ATTACK_LIKE_ACTION_TYPES:
            by_team[a.actor_team_id].append(a)

    actions_by_rally: dict[str, list[ActionRecord]] = defaultdict(list)
    for a in actions:
        actions_by_rally[a.rally_id].append(a)
    for rally_actions in actions_by_rally.values():
        rally_actions.sort(key=lambda a: a.sequence)

    result: dict[str, AttackStats] = {}
    for team_id, attacks in by_team.items():
        zone_counts: dict[Zone, int] = defaultdict(int)
        takeoff_position_counts: dict[str, int] = defaultdict(int)
        kills = errors = blocked = 0
        for atk in attacks:
            zone_counts[nearest_zone(atk.court_x, atk.court_y, "home")] += 1
            takeoff_position_counts[_takeoff_position_bucket(atk.court_x)] += 1
            if atk.outcome == "point":
                kills += 1
            elif atk.outcome == "error":
                errors += 1
                if atk.outcome_detail == "blocked":
                    blocked += 1
                elif atk.outcome_detail is None:
                    rally_actions = actions_by_rally[atk.rally_id]
                    idx = next((i for i, a in enumerate(rally_actions) if a.id == atk.id), None)
                    if idx is not None and idx + 1 < len(rally_actions):
                        nxt = rally_actions[idx + 1]
                        if nxt.action_type == "block" and nxt.actor_team_id != team_id:
                            blocked += 1
        total = len(attacks)
        result[team_id] = AttackStats(
            team_id=team_id,
            total_attacks=total,
            kills=kills,
            errors=errors,
            blocked=blocked,
            efficiency=_safe_div(kills - errors, total),
            zone_counts=dict(zone_counts),
            takeoff_position_counts=dict(takeoff_position_counts),
        )
    return result


# ---------------------------------------------------------------------------
# Block / dig
# ---------------------------------------------------------------------------


def compute_block_stats(actions: list[ActionRecord]) -> dict[str, BlockStats]:
    by_team: dict[str, list[ActionRecord]] = defaultdict(list)
    for a in actions:
        if a.action_type == "block":
            by_team[a.actor_team_id].append(a)

    result: dict[str, BlockStats] = {}
    for team_id, blocks in by_team.items():
        kills = sum(1 for b in blocks if b.outcome == "point")
        errors = sum(1 for b in blocks if b.outcome == "error")
        result[team_id] = BlockStats(
            team_id=team_id, total_blocks=len(blocks), block_kills=kills, block_errors=errors
        )
    return result


def compute_dig_stats(actions: list[ActionRecord]) -> dict[str, DigStats]:
    by_team: dict[str, list[ActionRecord]] = defaultdict(list)
    for a in actions:
        if a.action_type == "dig":
            by_team[a.actor_team_id].append(a)
    return {
        team_id: DigStats(team_id=team_id, total_digs=len(digs))
        for team_id, digs in by_team.items()
    }


# ---------------------------------------------------------------------------
# Sideout / breakpoint
# ---------------------------------------------------------------------------


def compute_sideout_breakpoint(
    rallies: list[RallyRecord], team_ids: set[str] | None = None
) -> dict[str, SideoutBreakpointStats]:
    """Breakpoint % (a.k.a. point-on-serve %): points won while serving /
    total rallies served. Sideout %: points won while receiving / total
    rallies received."""
    ids = team_ids or {r.serving_team_id for r in rallies}
    result: dict[str, SideoutBreakpointStats] = {}
    for team_id in ids:
        serve_rallies = [r for r in rallies if r.serving_team_id == team_id]
        reception_rallies = [r for r in rallies if r.serving_team_id != team_id]
        serve_won = sum(1 for r in serve_rallies if r.point_winner_team_id == team_id)
        reception_won = sum(1 for r in reception_rallies if r.point_winner_team_id == team_id)
        result[team_id] = SideoutBreakpointStats(
            team_id=team_id,
            serve_rallies=len(serve_rallies),
            serve_points_won=serve_won,
            breakpoint_pct=_safe_div(serve_won, len(serve_rallies)),
            reception_rallies=len(reception_rallies),
            reception_points_won=reception_won,
            sideout_pct=_safe_div(reception_won, len(reception_rallies)),
        )
    return result


# ---------------------------------------------------------------------------
# Setter distribution
# ---------------------------------------------------------------------------


def compute_setter_distribution(actions: list[ActionRecord]) -> dict[str, SetterDistributionEntry]:
    """For each 'set' action attributed to a roster entry, look at the next
    action (by `sequence`) in the same rally on the same team -- if it's an
    attack or a tip (both are "the ball got hit," see `_ATTACK_LIKE_ACTION_TYPES`
    in compute_attack_stats), count which zone it landed in. This is how
    setter tendencies get tracked without a separate "assist" relationship
    in the schema.

    Known limitation (flagged by independent domain review, not fixed
    here): "the very next same-team action" is a reasonable v1 proxy for
    clean plays, but under-attributes or drops the assist whenever a second
    player has to save/re-set an off-target set before the real hitter
    attacks -- a realistic, non-rare scenario on any imperfect first pass,
    not an edge case. A more correct design needs an explicit assist link
    (e.g. a `set_action_id` on Action) once real CV/human-reviewed data
    makes that link available; adjacency is a bootstrap, not the end state."""
    actions_by_rally: dict[str, list[ActionRecord]] = defaultdict(list)
    for a in actions:
        actions_by_rally[a.rally_id].append(a)
    for rally_actions in actions_by_rally.values():
        rally_actions.sort(key=lambda a: a.sequence)

    totals: dict[str, int] = defaultdict(int)
    followed: dict[str, int] = defaultdict(int)
    zones: dict[str, dict[Zone, int]] = defaultdict(lambda: defaultdict(int))

    for rally_actions in actions_by_rally.values():
        for i, a in enumerate(rally_actions):
            if a.action_type != "set" or a.actor_roster_id is None:
                continue
            totals[a.actor_roster_id] += 1
            if i + 1 < len(rally_actions):
                nxt = rally_actions[i + 1]
                if (
                    nxt.action_type in _ATTACK_LIKE_ACTION_TYPES
                    and nxt.actor_team_id == a.actor_team_id
                ):
                    followed[a.actor_roster_id] += 1
                    zones[a.actor_roster_id][nearest_zone(nxt.court_x, nxt.court_y, "home")] += 1

    return {
        setter_id: SetterDistributionEntry(
            setter_roster_id=setter_id,
            total_sets=totals[setter_id],
            followed_by_attack=followed.get(setter_id, 0),
            zone_counts=dict(zones.get(setter_id, {})),
        )
        for setter_id in totals
    }


# ---------------------------------------------------------------------------
# Rally duration
# ---------------------------------------------------------------------------


def compute_rally_duration_stats(rallies: list[RallyRecord]) -> RallyDurationStats:
    durations = [r.duration_seconds for r in rallies if r.duration_seconds is not None]
    if not durations:
        return RallyDurationStats(
            count=0, mean_seconds=None, median_seconds=None, min_seconds=None, max_seconds=None
        )
    return RallyDurationStats(
        count=len(durations),
        mean_seconds=mean(durations),
        median_seconds=median(durations),
        min_seconds=min(durations),
        max_seconds=max(durations),
    )


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


def compute_match_statistics(
    rallies: list[RallyRecord], actions: list[ActionRecord], config: StatsConfig = DEFAULT_CONFIG
) -> MatchStatistics:
    return MatchStatistics(
        formula_version=FORMULA_VERSION,
        serve=compute_serve_stats(actions),
        reception=compute_reception_stats(actions, config),
        attack=compute_attack_stats(actions),
        block=compute_block_stats(actions),
        dig=compute_dig_stats(actions),
        sideout_breakpoint=compute_sideout_breakpoint(rallies, _team_ids(actions, rallies)),
        setter_distribution=compute_setter_distribution(actions),
        rally_duration=compute_rally_duration_stats(rallies),
    )
