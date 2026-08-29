from volley_domain.court import nearest_zone
from volley_domain.synthetic.generator import generate_synthetic_match


def test_determinism_same_seed_same_output():
    a = generate_synthetic_match(seed=42, home_team="Alpha", away_team="Beta")
    b = generate_synthetic_match(seed=42, home_team="Alpha", away_team="Beta")
    # generated_at is wall-clock metadata; compare everything else.
    assert a.model_dump(exclude={"generated_at"}) == b.model_dump(exclude={"generated_at"})


def test_different_seeds_produce_different_matches():
    a = generate_synthetic_match(seed=1)
    b = generate_synthetic_match(seed=2)
    assert a.model_dump(exclude={"generated_at"}) != b.model_dump(exclude={"generated_at"})


def test_match_is_won_in_3_to_5_sets():
    match = generate_synthetic_match(seed=7)
    assert 3 <= len(match.sets) <= 5
    home_wins = sum(1 for s in match.sets if s.score.winner == "home")
    away_wins = sum(1 for s in match.sets if s.score.winner == "away")
    assert (home_wins, away_wins) in {(3, 0), (3, 1), (3, 2), (0, 3), (1, 3), (2, 3)}


def test_every_set_is_won_by_two_clear_points():
    match = generate_synthetic_match(seed=123)
    for s in match.sets:
        target = 15 if s.index == 4 else 25
        winning_score = max(s.score.home_points, s.score.away_points)
        losing_score = min(s.score.home_points, s.score.away_points)
        assert winning_score >= target
        assert winning_score - losing_score >= 2


def test_rosters_have_seven_unique_numbered_players():
    match = generate_synthetic_match(seed=5)
    for roster in (match.home_roster, match.away_roster):
        assert len(roster.players) == 7
        numbers = [p.jersey_number for p in roster.players]
        assert len(numbers) == len(set(numbers))


def test_court_coordinates_are_normalized():
    match = generate_synthetic_match(seed=9)
    for s in match.sets:
        for rally in s.rallies:
            for action in rally.actions:
                assert 0.0 <= action.court_x <= 1.0
                assert 0.0 <= action.court_y <= 1.0
            for pos in rally.player_positions:
                assert 0.0 <= pos.x <= 1.0
                assert 0.0 <= pos.y <= 1.0
            for ball in rally.ball_positions:
                assert 0.0 <= ball.x <= 1.0
                assert 0.0 <= ball.y <= 1.0
                assert ball.z >= 0.0


def test_ball_provenance_is_never_all_observed():
    """Sanity check that the synthetic provenance distribution actually
    exercises interpolated/predicted states, per ADR-001's rule that the UI
    must never be built assuming every ball point is 'observed'."""
    match = generate_synthetic_match(seed=11)
    provenances = {
        ball.provenance for s in match.sets for rally in s.rallies for ball in rally.ball_positions
    }
    assert "observed" in provenances
    assert "interpolated" in provenances or "predicted" in provenances


def test_every_rally_has_a_point_winner_and_nonempty_actions():
    match = generate_synthetic_match(seed=13)
    for s in match.sets:
        for rally in s.rallies:
            assert rally.point_winner in ("home", "away")
            assert len(rally.actions) >= 1
            assert rally.actions[-1].outcome in ("point", "error")


def test_summary_matches_full_match():
    match = generate_synthetic_match(seed=17)
    summary = match.summary()
    assert summary.total_rallies == sum(len(s.rallies) for s in match.sets)
    assert summary.sets_won_home + summary.sets_won_away == len(match.sets)


def test_serve_zone_attribution_is_identical_for_both_teams():
    """A serve from a team's own zone-1 anchor must resolve to zone 1
    regardless of which team served -- an earlier version mirrored the
    away team's coordinates, so an away-team zone-1 serve was reported as
    zone 4, silently corrupting every away-team zone statistic. Caught by
    independent architecture review with a live reproduction (measured on
    seed 42), not by any test until this one. See
    volley_domain.stats.records.ActionRecord's documented "own frame,
    unmirrored" contract."""
    for seed in range(10):
        match = generate_synthetic_match(seed=seed)
        home_serve_zones = {
            nearest_zone(a.court_x, a.court_y, "home")
            for s in match.sets
            for r in s.rallies
            for a in r.actions
            if a.type == "serve" and a.actor_team == "home"
        }
        away_serve_zones = {
            nearest_zone(a.court_x, a.court_y, "home")
            for s in match.sets
            for r in s.rallies
            for a in r.actions
            if a.type == "serve" and a.actor_team == "away"
        }
        assert home_serve_zones == {1}, f"seed={seed}: home not all zone 1: {home_serve_zones}"
        assert away_serve_zones == {1}, f"seed={seed}: away not all zone 1: {away_serve_zones}"


def test_no_team_ever_makes_more_than_three_consecutive_contacts():
    """FIVB Rule 9.3: a team may not contact the ball more than three times
    (not counting a block touch) before it must cross the net. An earlier
    version of the exchange loop produced a real violation of this (dig ->
    transition -> set -> attack, 4 consecutive same-team touches) that no
    test caught until an independent domain review traced it by hand -- see
    ADR-004 / PROJECT_STATUS.md. This test exists specifically so that
    regression can never ship silently again."""
    for seed in range(30):
        match = generate_synthetic_match(seed=seed)
        for s in match.sets:
            for rally in s.rallies:
                consecutive = 1
                for i in range(1, len(rally.actions)):
                    if rally.actions[i].actor_team == rally.actions[i - 1].actor_team:
                        consecutive += 1
                        assert consecutive <= 3, (
                            f"seed={seed} rally={rally.id}: team "
                            f"{rally.actions[i].actor_team!r} made {consecutive} "
                            f"consecutive contacts (actions {[a.type for a in rally.actions]})"
                        )
                    else:
                        consecutive = 1
