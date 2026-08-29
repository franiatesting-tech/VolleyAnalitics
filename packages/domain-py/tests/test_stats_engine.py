"""Known-input/known-output tests per statistic, per docs/domain/ONTOLOGY.md's
"Statistics engine" section. Each test constructs a small, hand-verifiable
scenario (not the synthetic generator's random output) so the expected
number is something a human checked, not something the engine itself
produced -- see test_lineage.py and test_synthetic_generator.py for the
other two families of domain tests.
"""

from volley_domain.stats.engine import (
    DEFAULT_CONFIG,
    ReceptionRatingScale,
    StatsConfig,
    compute_attack_stats,
    compute_block_stats,
    compute_dig_stats,
    compute_match_statistics,
    compute_rally_duration_stats,
    compute_reception_stats,
    compute_serve_stats,
    compute_setter_distribution,
    compute_sideout_breakpoint,
)
from volley_domain.stats.records import ActionRecord, RallyRecord

HOME, AWAY = "team-home", "team-away"


def _action(
    seq: int, action_type, team, outcome=None, x=0.5, y=0.5, roster=None, rally="r1", rating=None
):
    return ActionRecord(
        id=f"a{seq}",
        rally_id=rally,
        sequence=seq,
        action_type=action_type,
        actor_team_id=team,
        actor_roster_id=roster,
        outcome=outcome,
        court_x=x,
        court_y=y,
        quality_rating=rating,
    )


# ---------------------------------------------------------------------------
# Serve: aces, errors, zone attribution
# ---------------------------------------------------------------------------


def test_serve_stats_counts_aces_and_errors():
    actions = [
        _action(1, "serve", HOME, outcome="point"),  # ace
        _action(2, "serve", HOME, outcome="error"),  # serve error
        _action(3, "serve", HOME, outcome="continue"),  # in play
    ]
    stats = compute_serve_stats(actions)
    assert stats[HOME].total_serves == 3
    assert stats[HOME].aces == 1
    assert stats[HOME].serve_errors == 1


def test_serve_stats_zone_attribution_uses_nearest_zone():
    # Zone 1's anchor is (0.83, 0.92) -- see court.py.
    actions = [_action(1, "serve", HOME, outcome="continue", x=0.83, y=0.92)]
    stats = compute_serve_stats(actions)
    assert stats[HOME].zone_counts == {1: 1}


def test_serve_stats_empty_for_team_with_no_serves():
    assert compute_serve_stats([]) == {}


# ---------------------------------------------------------------------------
# Reception: configurable rating scale
# ---------------------------------------------------------------------------


def test_reception_average_rating_and_effectiveness_default_scale():
    # Default scale: effective_threshold=2.0. Average of [3, 1] = 2.0 -> effective.
    actions = [
        _action(1, "reception", HOME, rating=3),
        _action(2, "reception", HOME, rating=1),
    ]
    stats = compute_reception_stats(actions)
    assert stats[HOME].total_receptions == 2
    assert stats[HOME].rated_receptions == 2
    assert stats[HOME].average_rating == 2.0
    assert stats[HOME].is_effective is True


def test_reception_below_threshold_is_not_effective():
    actions = [_action(1, "reception", HOME, rating=0), _action(2, "reception", HOME, rating=1)]
    stats = compute_reception_stats(actions)
    assert stats[HOME].average_rating == 0.5
    assert stats[HOME].is_effective is False


def test_reception_rating_scale_is_configurable_not_hardcoded():
    """A program using a stricter effective_threshold should get a
    different is_effective verdict for the exact same data -- proves the
    scale is actually threaded through, not a hardcoded 2.0."""
    actions = [_action(1, "reception", HOME, rating=2), _action(2, "reception", HOME, rating=2)]
    lenient = compute_reception_stats(
        actions, StatsConfig(ReceptionRatingScale(effective_threshold=1.5))
    )
    strict = compute_reception_stats(
        actions, StatsConfig(ReceptionRatingScale(effective_threshold=2.5))
    )
    assert lenient[HOME].is_effective is True
    assert strict[HOME].is_effective is False


def test_reception_unrated_actions_produce_no_average():
    actions = [_action(1, "reception", HOME, rating=None)]
    stats = compute_reception_stats(actions)
    assert stats[HOME].average_rating is None
    assert stats[HOME].is_effective is None


# ---------------------------------------------------------------------------
# Attack: efficiency formula (verified against SDHSAA/NCAA convention)
# ---------------------------------------------------------------------------


def test_attack_efficiency_formula_kills_minus_errors_over_total():
    # 3 kills, 1 error, 6 total attempts -> (3 - 1) / 6 = 0.333...
    actions = [
        _action(1, "attack", HOME, outcome="point"),
        _action(2, "attack", HOME, outcome="point"),
        _action(3, "attack", HOME, outcome="point"),
        _action(4, "attack", HOME, outcome="error"),
        _action(5, "attack", HOME, outcome="continue"),
        _action(6, "attack", HOME, outcome="continue"),
    ]
    stats = compute_attack_stats(actions)
    assert stats[HOME].kills == 3
    assert stats[HOME].errors == 1
    assert stats[HOME].total_attacks == 6
    assert stats[HOME].efficiency == (3 - 1) / 6


def test_attack_efficiency_classic_worked_example():
    """The exact 20/5/30 example from SDHSAA's guidelines: (20-5)/30 = 0.50."""
    actions = (
        [_action(i, "attack", HOME, outcome="point") for i in range(20)]
        + [_action(20 + i, "attack", HOME, outcome="error") for i in range(5)]
        + [_action(25 + i, "attack", HOME, outcome="continue") for i in range(5)]
    )
    stats = compute_attack_stats(actions)
    assert stats[HOME].total_attacks == 30
    assert stats[HOME].efficiency == 0.5


def test_attack_efficiency_is_none_with_zero_attempts():
    assert compute_attack_stats([]) == {}


def test_attack_blocked_count_requires_immediately_following_opposing_block():
    actions = [
        _action(1, "attack", HOME, outcome="error", rally="r1"),
        _action(2, "block", AWAY, outcome="point", rally="r1"),
    ]
    stats = compute_attack_stats(actions)
    assert stats[HOME].blocked == 1
    assert stats[HOME].errors == 1


def test_attack_error_not_counted_as_blocked_without_a_following_block():
    actions = [_action(1, "attack", HOME, outcome="error", rally="r1")]
    stats = compute_attack_stats(actions)
    assert stats[HOME].blocked == 0


def test_attack_takeoff_position_bucketing():
    actions = [
        _action(1, "attack", HOME, outcome="continue", x=0.1),  # left
        _action(2, "attack", HOME, outcome="continue", x=0.5),  # middle
        _action(3, "attack", HOME, outcome="continue", x=0.9),  # right
    ]
    stats = compute_attack_stats(actions)
    assert stats[HOME].takeoff_position_counts == {"left": 1, "middle": 1, "right": 1}


def test_tip_actions_count_as_attacks_not_a_separate_dropped_category():
    """A tip is a shot-selection variant of an attack in standard
    scorekeeping -- it must count toward kills/errors/attempts/efficiency
    exactly like a hard-driven attack, not vanish from these stats. An
    earlier version filtered on action_type == "attack" only and silently
    dropped every tip kill/error, caught by independent domain review."""
    actions = [
        _action(1, "attack", HOME, outcome="point"),
        _action(2, "tip", HOME, outcome="point"),
        _action(3, "tip", HOME, outcome="error"),
    ]
    stats = compute_attack_stats(actions)
    assert stats[HOME].total_attacks == 3
    assert stats[HOME].kills == 2
    assert stats[HOME].errors == 1
    assert stats[HOME].efficiency == (2 - 1) / 3


def test_tip_only_team_is_not_silently_excluded_from_attack_stats():
    """Before the fix, a team with only tip actions (no plain 'attack' rows)
    would produce no AttackStats entry at all for that team."""
    actions = [_action(1, "tip", AWAY, outcome="point")]
    stats = compute_attack_stats(actions)
    assert AWAY in stats
    assert stats[AWAY].kills == 1


# ---------------------------------------------------------------------------
# Block / dig
# ---------------------------------------------------------------------------


def test_block_stats_kills_and_errors():
    actions = [
        _action(1, "block", HOME, outcome="point"),
        _action(2, "block", HOME, outcome="error"),
        _action(3, "block", HOME, outcome="continue"),
    ]
    stats = compute_block_stats(actions)
    assert stats[HOME].total_blocks == 3
    assert stats[HOME].block_kills == 1
    assert stats[HOME].block_errors == 1


def test_dig_stats_counts():
    actions = [_action(1, "dig", HOME), _action(2, "dig", HOME), _action(3, "dig", AWAY)]
    stats = compute_dig_stats(actions)
    assert stats[HOME].total_digs == 2
    assert stats[AWAY].total_digs == 1


# ---------------------------------------------------------------------------
# Sideout / breakpoint
# ---------------------------------------------------------------------------


def test_sideout_and_breakpoint_percentages():
    rallies = [
        RallyRecord(id="r1", serving_team_id=HOME, point_winner_team_id=HOME),  # HOME breakpoint
        RallyRecord(id="r2", serving_team_id=HOME, point_winner_team_id=AWAY),  # AWAY sideout
        RallyRecord(id="r3", serving_team_id=AWAY, point_winner_team_id=HOME),  # HOME sideout
        RallyRecord(id="r4", serving_team_id=AWAY, point_winner_team_id=AWAY),  # AWAY breakpoint
    ]
    stats = compute_sideout_breakpoint(rallies)
    # HOME served r1,r2 (won 1/2 = 0.5 breakpoint); received r3,r4 (won 1/2 = 0.5 sideout)
    assert stats[HOME].serve_rallies == 2
    assert stats[HOME].serve_points_won == 1
    assert stats[HOME].breakpoint_pct == 0.5
    assert stats[HOME].reception_rallies == 2
    assert stats[HOME].reception_points_won == 1
    assert stats[HOME].sideout_pct == 0.5


def test_sideout_breakpoint_handles_zero_rallies():
    stats = compute_sideout_breakpoint([], team_ids={HOME})
    assert stats[HOME].breakpoint_pct is None
    assert stats[HOME].sideout_pct is None


# ---------------------------------------------------------------------------
# Setter distribution
# ---------------------------------------------------------------------------


def test_setter_distribution_tracks_zone_of_following_attack():
    actions = [
        _action(1, "set", HOME, roster="setter-1", rally="r1"),
        _action(2, "attack", HOME, outcome="point", x=0.83, y=0.58, rally="r1"),  # zone 2
        _action(3, "set", HOME, roster="setter-1", rally="r2"),
        _action(4, "attack", HOME, outcome="point", x=0.17, y=0.58, rally="r2"),  # zone 4
    ]
    dist = compute_setter_distribution(actions)
    assert dist["setter-1"].total_sets == 2
    assert dist["setter-1"].followed_by_attack == 2
    assert dist["setter-1"].zone_counts == {2: 1, 4: 1}


def test_setter_distribution_ignores_sets_with_no_roster_attribution():
    actions = [_action(1, "set", HOME, roster=None)]
    assert compute_setter_distribution(actions) == {}


def test_setter_distribution_does_not_count_opposing_teams_next_action():
    """If the very next action belongs to the other team (e.g. the set led
    to a turnover before an attack happened), it must not be misread as
    this setter's distribution target."""
    actions = [
        _action(1, "set", HOME, roster="setter-1", rally="r1"),
        _action(2, "dig", AWAY, rally="r1"),
    ]
    dist = compute_setter_distribution(actions)
    assert dist["setter-1"].total_sets == 1
    assert dist["setter-1"].followed_by_attack == 0


def test_setter_distribution_counts_a_following_tip_as_followed_by_attack():
    """A tip is attack-like for setter-distribution purposes too -- a
    setter whose set led to a tip kill was still "followed by an attack"
    in the sense this stat measures."""
    actions = [
        _action(1, "set", HOME, roster="setter-1", rally="r1"),
        _action(2, "tip", HOME, outcome="point", x=0.83, y=0.58, rally="r1"),  # zone 2
    ]
    dist = compute_setter_distribution(actions)
    assert dist["setter-1"].followed_by_attack == 1
    assert dist["setter-1"].zone_counts == {2: 1}


# ---------------------------------------------------------------------------
# Rally duration
# ---------------------------------------------------------------------------


def test_rally_duration_stats():
    rallies = [
        RallyRecord(id="r1", serving_team_id=HOME, point_winner_team_id=HOME, duration_seconds=4.0),
        RallyRecord(id="r2", serving_team_id=HOME, point_winner_team_id=HOME, duration_seconds=8.0),
        RallyRecord(
            id="r3", serving_team_id=HOME, point_winner_team_id=HOME, duration_seconds=12.0
        ),
    ]
    stats = compute_rally_duration_stats(rallies)
    assert stats.count == 3
    assert stats.mean_seconds == 8.0
    assert stats.median_seconds == 8.0
    assert stats.min_seconds == 4.0
    assert stats.max_seconds == 12.0


def test_rally_duration_stats_empty():
    stats = compute_rally_duration_stats([])
    assert stats.count == 0
    assert stats.mean_seconds is None


# ---------------------------------------------------------------------------
# Top-level aggregation + formula versioning
# ---------------------------------------------------------------------------


def test_match_statistics_carries_formula_version():
    result = compute_match_statistics([], [], DEFAULT_CONFIG)
    assert result.formula_version  # non-empty, present on every result


def test_match_statistics_aggregates_all_categories():
    rallies = [RallyRecord(id="r1", serving_team_id=HOME, point_winner_team_id=HOME)]
    actions = [_action(1, "serve", HOME, outcome="point", rally="r1")]
    result = compute_match_statistics(rallies, actions)
    assert HOME in result.serve
    assert HOME in result.sideout_breakpoint
    assert result.rally_duration.count == 0  # no duration_seconds set on this rally
