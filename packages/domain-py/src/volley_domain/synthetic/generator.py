"""Deterministic synthetic-match generator.

Purpose: let the whole frontend (Match Analysis, Rally Explorer, replay,
stats views) be built and demoed before any real CV/tracking pipeline
exists, per ROADMAP.md Phase 1. Every value here is clearly synthetic --
this module must never be imported by anything that also touches real
Prediction/Event data (see docs/architecture/DATA_FLOW.md's entity
separation) and its outputs must never be presented to a user as if they
came from real video.

Determinism: identical `seed` always produces an identical SyntheticMatch.
Uses only `random.Random(seed)`, no global random state, no wall-clock
inputs except `generated_at` (which is metadata, not simulation input).

Court coordinates: every action/position uses `court.ZONE_ANCHORS` directly,
unmirrored, for both teams -- per volley_domain.stats.records.ActionRecord's
documented contract that court_x/court_y are always in the *acting team's
own* attacking frame. An earlier version called `court.zone_anchor(zone,
team)`, which mirrors for the away team -- that silently broke every
away-team zone statistic (a zone-1 serve was reported as zone 4), caught by
independent architecture review with a live reproduction, not by any test.
Mirroring (`court.mirror_for_away`) remains available for rendering both
teams on one shared visual frame later -- it must never be baked into what
gets persisted as ground truth.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

from volley_domain.court import ZONE_ANCHORS, Zone
from volley_domain.schemas import (
    ActionOutcome,
    ActionType,
    BallPositionSample,
    BallProvenance,
    PlayerPositionSample,
    RosterPlayer,
    RosterPosition,
    SyntheticAction,
    SyntheticMatch,
    SyntheticRally,
    SyntheticSet,
    SyntheticSetScore,
    Team,
    TeamRoster,
)

_POSITIONS: list[RosterPosition] = ["OH", "OH", "MB", "MB", "S", "OP", "L"]  # 7-player roster shape


def _det_id(rng: random.Random) -> str:
    """Deterministic pseudo-UUID drawn from the seeded RNG -- module-level
    uuid.uuid4() reads OS entropy and would silently break determinism."""
    return f"{rng.getrandbits(128):032x}"


def _make_roster(rng: random.Random, team_name: str) -> TeamRoster:
    used_numbers: set[int] = set()
    players: list[RosterPlayer] = []
    for i, position in enumerate(_POSITIONS):
        number = rng.randint(1, 99)
        while number in used_numbers:
            number = rng.randint(1, 99)
        used_numbers.add(number)
        players.append(
            RosterPlayer(
                id=_det_id(rng),
                name=f"{team_name} Player {i + 1}",
                jersey_number=number,
                position=position,
            )
        )
    return TeamRoster(team_name=team_name, players=players)


def _players_by_position(roster: TeamRoster, position: RosterPosition) -> list[RosterPlayer]:
    return [p for p in roster.players if p.position == position]


def _pick(rng: random.Random, players: list[RosterPlayer]) -> RosterPlayer:
    return rng.choice(players)


def _build_action_chain(
    rng: random.Random,
    serving_team: Team,
    receiving_team: Team,
    point_winner: Team,
    rosters: dict[Team, TeamRoster],
) -> list[SyntheticAction]:
    """Actions' t_start/t_end are deliberately rally-relative (0.0 at the
    rally's first action), matching PlayerPositionSample.t's "seconds from
    rally start" contract and keeping ball-position sampling (which derives
    its own timestamps from these) internally consistent. The match-
    absolute clock (SyntheticRally.match_t_start/end) is tracked separately
    at the _simulate_set level, not threaded into this function -- an
    earlier draft of this fix tried offsetting `t` here directly, which
    would have made ball-position timestamps match-absolute while
    player-position timestamps stayed rally-relative, a new inconsistency
    within the same rally. Caught before it shipped."""
    actions: list[SyntheticAction] = []
    t = 0.0

    def add(
        action_type: ActionType,
        team: Team,
        actor: RosterPlayer,
        duration: float,
        outcome: ActionOutcome,
        court_xy: tuple[float, float],
    ) -> None:
        nonlocal t
        x, y = court_xy
        actions.append(
            SyntheticAction(
                id=_det_id(rng),
                t_start=round(t, 3),
                t_end=round(t + duration, 3),
                type=action_type,
                actor_player_id=actor.id,
                actor_team=team,
                outcome=outcome,
                confidence=round(rng.uniform(0.82, 0.99), 3),
                court_x=round(x, 4),
                court_y=round(y, 4),
            )
        )
        t += duration

    server_roster = rosters[serving_team]
    receiver_roster = rosters[receiving_team]
    server = _pick(rng, [p for p in server_roster.players if p.position != "L"])
    serve_xy = ZONE_ANCHORS[1]

    # Rally length: mostly short (ace / serve error / quick kill), sometimes long.
    rally_shape = rng.choices(["ace", "serve_error", "short", "long"], weights=[10, 6, 54, 30])[0]

    if rally_shape == "ace":
        add("serve", serving_team, server, 0.9, "point", serve_xy)
        return actions

    if rally_shape == "serve_error":
        add("serve", serving_team, server, 0.9, "error", serve_xy)
        return actions

    add("serve", serving_team, server, 0.9, "continue", serve_xy)

    libero = _players_by_position(receiver_roster, "L")
    receiver = libero[0] if libero and rng.random() < 0.6 else _pick(rng, receiver_roster.players)
    recv_zone = ZONE_ANCHORS[5]
    add("reception", receiving_team, receiver, 0.4, "continue", recv_zone)

    exchanges = 1 if rally_shape == "short" else rng.randint(2, 4)
    current_team, other_team = receiving_team, serving_team

    for exchange_i in range(exchanges):
        setter = _pick(
            rng, _players_by_position(rosters[current_team], "S") or rosters[current_team].players
        )
        set_zone = ZONE_ANCHORS[3]
        add("set", current_team, setter, 0.3, "continue", set_zone)

        attacker_pool = [
            p for p in rosters[current_team].players if p.position in ("OH", "OP", "MB")
        ]
        attacker = _pick(rng, attacker_pool)
        attack_zone_options: list[Zone] = [2, 3, 4]
        attack_zone_key = rng.choice(attack_zone_options)
        attack_zone = ZONE_ANCHORS[attack_zone_key]
        is_last_exchange = exchange_i == exchanges - 1
        if is_last_exchange:
            attack_outcome = "point" if point_winner == current_team else "error"
            if attack_outcome == "error":
                add("attack", current_team, attacker, 0.5, "error", attack_zone)
                return actions
            # Point could be a clean kill, or a dig/block sequence first.
            defended = rng.random() < 0.35
            if not defended:
                add("attack", current_team, attacker, 0.5, "point", attack_zone)
                return actions
            add("attack", current_team, attacker, 0.5, "continue", attack_zone)
            defender = _pick(rng, rosters[other_team].players)
            def_zone = ZONE_ANCHORS[6]
            def_type_options: list[ActionType] = ["block", "dig"]
            def_type = rng.choice(def_type_options)
            def_outcome = "error" if def_type == "block" else "continue"
            add(def_type, other_team, defender, 0.3, def_outcome, def_zone)
            if def_outcome == "error":
                return actions
            add(
                "free_ball",
                current_team,
                _pick(rng, rosters[current_team].players),
                0.4,
                "point" if point_winner == current_team else "error",
                attack_zone,
            )
            return actions
        else:
            # Exactly 3 team touches per exchange: set + attack (above) by
            # current_team, then dig by other_team. Do NOT add a further
            # standalone "transition" action here -- an earlier version did,
            # which meant this team's *next* iteration set+attack (as the
            # new current_team) landed as a 4th consecutive same-team touch
            # with no intervening contact from the opponent, violating the
            # real 3-touches-per-side rule (FIVB 9.3). Caught by independent
            # domain review, not by any test -- persistence tests checked
            # row counts/phase grouping/coordinates but never contact-count
            # legality. The dig below is this team's *first* touch of their
            # next possession; their following set+attack (added at the top
            # of the next loop iteration) are touches 2 and 3.
            add("attack", current_team, attacker, 0.5, "continue", attack_zone)
            defender = _pick(rng, rosters[other_team].players)
            def_zone = ZONE_ANCHORS[6]
            add("dig", other_team, defender, 0.3, "continue", def_zone)
            current_team, other_team = other_team, current_team

    return actions


def _sample_player_positions(
    rng: random.Random, rosters: dict[Team, TeamRoster], duration: float, n_samples: int
) -> list[PlayerPositionSample]:
    samples: list[PlayerPositionSample] = []
    base_by_player: dict[str, tuple[float, float, Team]] = {}
    court_slots: list[Zone] = [1, 2, 3, 4, 5, 6]
    for team_key, roster in rosters.items():
        on_court = roster.players[:6]  # simplified: first 6 of 7 are "on court" this rally
        for slot, player in zip(court_slots, on_court, strict=False):
            xy = ZONE_ANCHORS[slot]
            base_by_player[player.id] = (*xy, team_key)

    for i in range(n_samples):
        t = round(duration * i / max(1, n_samples - 1), 3)
        for player_id, (bx, by, team_key) in base_by_player.items():
            jitter_x = rng.uniform(-0.04, 0.04)
            jitter_y = rng.uniform(-0.04, 0.04)
            samples.append(
                PlayerPositionSample(
                    t=t,
                    player_id=player_id,
                    team=team_key,
                    x=min(1.0, max(0.0, bx + jitter_x)),
                    y=min(1.0, max(0.0, by + jitter_y)),
                )
            )
    return samples


def _sample_ball_positions(
    rng: random.Random, actions: list[SyntheticAction], n_per_action: int = 3
) -> list[BallPositionSample]:
    samples: list[BallPositionSample] = []
    prev_xy = (actions[0].court_x, actions[0].court_y) if actions else (0.5, 0.5)
    for action in actions:
        target_xy = (action.court_x, action.court_y)
        for i in range(n_per_action):
            frac = (i + 1) / n_per_action
            t = round(action.t_start + (action.t_end - action.t_start) * frac, 3)
            x = prev_xy[0] + (target_xy[0] - prev_xy[0]) * frac
            y = prev_xy[1] + (target_xy[1] - prev_xy[1]) * frac
            arc_z = max(0.0, 1.0 - abs(frac - 0.5) * 2) * rng.uniform(0.6, 1.0)
            provenance_options: list[BallProvenance] = ["observed", "interpolated", "predicted"]
            provenance = rng.choices(provenance_options, weights=[70, 22, 8])[0]
            confidence = {
                "observed": rng.uniform(0.9, 0.99),
                "interpolated": rng.uniform(0.7, 0.9),
                "predicted": rng.uniform(0.4, 0.7),
            }[provenance]
            samples.append(
                BallPositionSample(
                    t=t,
                    x=round(min(1.0, max(0.0, x)), 4),
                    y=round(min(1.0, max(0.0, y)), 4),
                    z=round(arc_z, 4),
                    provenance=provenance,
                    confidence=round(confidence, 3),
                )
            )
        prev_xy = target_xy
    return samples


_INTER_RALLY_GAP_SECONDS = 3.0  # referee reset / next-serve setup, deterministic (not rng-driven)


def _simulate_set(
    rng: random.Random,
    set_index: int,
    rosters: dict[Team, TeamRoster],
    home_skill: float,
    is_final_set: bool,
    first_serve: Team,
    match_clock_start: float,
) -> tuple[SyntheticSet, float]:
    """Returns the set and the match clock's position after it, so the
    caller can carry it into the next set -- see match_clock in
    generate_synthetic_match. `match_clock_start` is this set's own start
    position on that same running clock (seconds since set 1 began)."""
    target = 15 if is_final_set else 25
    home_points = 0
    away_points = 0
    serving_team = first_serve
    rallies: list[SyntheticRally] = []
    match_clock = match_clock_start

    while True:
        leading = max(home_points, away_points)
        if leading >= target and abs(home_points - away_points) >= 2:
            break
        if leading >= 40:  # safety cap, never realistically reached
            break

        receiving_team = "away" if serving_team == "home" else "home"
        serve_win_prob = home_skill if serving_team == "home" else (1 - home_skill)
        # servers win the rally slightly less often than they win the point
        # overall skill differential; sideout volleyball => most points are
        # won by the receiving/attacking team.
        point_to_server = rng.random() < (serve_win_prob * 0.42 + 0.5 * (serve_win_prob - 0.5))
        point_winner = serving_team if point_to_server else receiving_team

        actions = _build_action_chain(rng, serving_team, receiving_team, point_winner, rosters)
        duration = actions[-1].t_end if actions else 1.0
        rally = SyntheticRally(
            id=_det_id(rng),
            index_in_set=len(rallies),
            serving_team=serving_team,
            point_winner=point_winner,
            actions=actions,
            player_positions=_sample_player_positions(rng, rosters, duration, n_samples=6),
            ball_positions=_sample_ball_positions(rng, actions),
            duration_seconds=duration,
            match_t_start=round(match_clock, 3),
            match_t_end=round(match_clock + duration, 3),
        )
        rallies.append(rally)
        match_clock += duration + _INTER_RALLY_GAP_SECONDS

        if point_winner == "home":
            home_points += 1
        else:
            away_points += 1
        serving_team = point_winner  # winner serves next

    winner = "home" if home_points > away_points else "away"
    played_set = SyntheticSet(
        index=set_index,
        score=SyntheticSetScore(home_points=home_points, away_points=away_points, winner=winner),
        rallies=rallies,
    )
    return played_set, match_clock


def generate_synthetic_match(
    seed: int, home_team: str = "Home Volleyball Club", away_team: str = "Away Volleyball Club"
) -> SyntheticMatch:
    """Pure, deterministic: same seed + team names => byte-identical output
    (aside from `generated_at`, which is wall-clock metadata)."""
    rng = random.Random(seed)
    home_roster = _make_roster(rng, home_team)
    away_roster = _make_roster(rng, away_team)
    rosters: dict[Team, TeamRoster] = {"home": home_roster, "away": away_roster}

    # Skill differential derived from seed, kept in a realistic band so
    # matches aren't always blowouts or always coin-flips.
    home_skill = 0.5 + rng.uniform(-0.12, 0.12)

    sets: list[SyntheticSet] = []
    home_sets_won = 0
    away_sets_won = 0
    set_index = 0
    match_clock = 0.0  # seconds since set 1's first serve; carries across sets
    while home_sets_won < 3 and away_sets_won < 3:
        is_final = home_sets_won == 2 and away_sets_won == 2
        first_serve: Team = "home" if set_index % 2 == 0 else "away"
        played_set, match_clock = _simulate_set(
            rng, set_index, rosters, home_skill, is_final, first_serve, match_clock
        )
        sets.append(played_set)
        if played_set.score.winner == "home":
            home_sets_won += 1
        else:
            away_sets_won += 1
        set_index += 1

    return SyntheticMatch(
        seed=seed,
        home_roster=home_roster,
        away_roster=away_roster,
        sets=sets,
        generated_at=datetime.now(UTC),
    )
