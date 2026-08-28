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
