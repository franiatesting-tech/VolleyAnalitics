"""Verifies persist_synthetic_match actually writes a coherent ontology
graph against a real (SQLite) database -- this is what pays down the
"synthetic match stored as a JSON blob" tech debt entry."""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from volley_domain.base import Base
from volley_domain.models import Match, MatchStatus
from volley_domain.ontology import (
    Action,
    ModelRun,
    Outcome,
    Phase,
    Player,
    Rally,
    Roster,
    Season,
    Team,
)
from volley_domain.ontology import MatchSet as MatchSetRow
from volley_domain.synthetic.generator import generate_synthetic_match
from volley_domain.synthetic.persistence import persist_synthetic_match


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_match(db: Session, organization_id: str = "org-1") -> Match:
    match = Match(
        organization_id=organization_id,
        home_team="Alpha VC",
        away_team="Beta VC",
        status=MatchStatus.PROCESSING,
        created_by_user_id="user-1",
    )
    db.add(match)
    db.commit()
    return match


def test_persist_synthetic_match_writes_all_sets_and_rallies(db):
    match = _make_match(db)
    synthetic = generate_synthetic_match(seed=42, home_team="Alpha VC", away_team="Beta VC")

    persist_synthetic_match(db, organization_id="org-1", match_id=match.id, synthetic=synthetic)
    db.commit()

    set_count = db.scalar(
        select(func.count()).select_from(MatchSetRow).where(MatchSetRow.match_id == match.id)
    )
    assert set_count == len(synthetic.sets)

    total_rallies = sum(len(s.rallies) for s in synthetic.sets)
    rally_count = db.scalar(
        select(func.count())
        .select_from(Rally)
        .join(MatchSetRow, Rally.set_id == MatchSetRow.id)
        .where(MatchSetRow.match_id == match.id)
    )
    assert rally_count == total_rallies


def test_persist_synthetic_match_action_count_matches_generator_output(db):
    match = _make_match(db)
    synthetic = generate_synthetic_match(seed=7, home_team="Alpha VC", away_team="Beta VC")
    expected_actions = sum(len(r.actions) for s in synthetic.sets for r in s.rallies)

    persist_synthetic_match(db, organization_id="org-1", match_id=match.id, synthetic=synthetic)
    db.commit()

    actual_actions = db.scalar(select(func.count()).select_from(Action))
    assert actual_actions == expected_actions

    # Every Action has exactly one Outcome (1:1, per ONTOLOGY.md).
    actual_outcomes = db.scalar(select(func.count()).select_from(Outcome))
    assert actual_outcomes == expected_actions


def test_persist_synthetic_match_writes_outcome_detail_for_blocked_attacks(db):
    """Outcome.detail must round-trip from SyntheticAction.detail -- this
    is what lets compute_attack_stats trust an explicit "blocked" label
    instead of only the adjacency heuristic. Regression for TECH_DEBT.md's
    now-fixed 'blocked attack heuristic never exercised' entry."""
    match = _make_match(db)
    synthetic = generate_synthetic_match(seed=3, home_team="Alpha VC", away_team="Beta VC")
    blocked_synthetic_action_ids = {
        a.id for s in synthetic.sets for r in s.rallies for a in r.actions if a.detail == "blocked"
    }
    assert blocked_synthetic_action_ids, "seed=3 expected at least one blocked attack"

    persist_synthetic_match(db, organization_id="org-1", match_id=match.id, synthetic=synthetic)
    db.commit()

    detail_by_action_id = dict(db.execute(select(Action.id, Outcome.detail).join(Outcome)).all())
    # persist_synthetic_match mints fresh Action ids, so match by count/value
    # instead of by id -- the actual assertion is that some real, persisted
    # Outcome row carries detail == "blocked", not zero.
    persisted_blocked_count = sum(1 for v in detail_by_action_id.values() if v == "blocked")
    assert persisted_blocked_count == len(blocked_synthetic_action_ids)


def test_persist_synthetic_match_every_action_links_to_the_synthetic_model_run(db):
    match = _make_match(db)
    synthetic = generate_synthetic_match(seed=3, home_team="Alpha VC", away_team="Beta VC")

    pipeline_run = persist_synthetic_match(
        db, organization_id="org-1", match_id=match.id, synthetic=synthetic
    )
    db.commit()

    model_run = db.execute(
        select(ModelRun).where(ModelRun.pipeline_run_id == pipeline_run.id)
    ).scalar_one()
    unlinked = db.scalar(
        select(func.count()).select_from(Action).where(Action.model_run_id != model_run.id)
    )
    assert unlinked == 0, "every synthetic Action must carry the ModelRun's provenance"


def test_persist_synthetic_match_phases_group_by_actor_team(db):
    """A Phase must never contain actions from two different teams -- that
    would violate "Phase groups Actions by which team currently has the
    ball" from ONTOLOGY.md."""
    match = _make_match(db)
    synthetic = generate_synthetic_match(seed=11, home_team="Alpha VC", away_team="Beta VC")

    persist_synthetic_match(db, organization_id="org-1", match_id=match.id, synthetic=synthetic)
    db.commit()

    phases = db.execute(select(Phase)).scalars().all()
    for phase in phases:
        actions = db.execute(select(Action).where(Action.phase_id == phase.id)).scalars().all()
        team_ids = {a.actor_team_id for a in actions}
        assert len(team_ids) <= 1, f"phase {phase.id} mixes actions from {len(team_ids)} teams"


def test_persist_synthetic_match_action_coordinates_stay_in_bounds(db):
    match = _make_match(db)
    synthetic = generate_synthetic_match(seed=99, home_team="Alpha VC", away_team="Beta VC")

    persist_synthetic_match(db, organization_id="org-1", match_id=match.id, synthetic=synthetic)
    db.commit()

    actions = db.execute(select(Action)).scalars().all()
    assert len(actions) > 0
    for action in actions:
        assert 0.0 <= action.court_x <= 1.0
        assert 0.0 <= action.court_y <= 1.0


def test_persist_synthetic_match_timestamps_are_match_absolute_not_clustered_at_zero(db):
    """An earlier version reset every rally's action timestamps to start at
    0.0 and wrote them straight through, so every rally in a multi-set
    match claimed the same ~0-12s window and Rally.video_t_start was never
    even set (always None). Caught by independent architecture review.
    This test proves timestamps now span the real match duration and are
    strictly increasing rally-to-rally."""
    match = _make_match(db)
    synthetic = generate_synthetic_match(seed=42, home_team="Alpha VC", away_team="Beta VC")

    persist_synthetic_match(db, organization_id="org-1", match_id=match.id, synthetic=synthetic)
    db.commit()

    rallies = (
        db.execute(
            select(Rally)
            .join(MatchSetRow, Rally.set_id == MatchSetRow.id)
            .where(MatchSetRow.match_id == match.id)
            .order_by(Rally.video_t_start)
        )
        .scalars()
        .all()
    )
    assert len(rallies) > 10
    assert all(r.video_t_start is not None and r.video_t_end is not None for r in rallies)
    assert all(r.video_t_end > r.video_t_start for r in rallies)
    for earlier, later in zip(rallies, rallies[1:], strict=False):
        assert later.video_t_start >= earlier.video_t_end, "rallies must not overlap in match time"
    # Not clustered in a single rally's worth of seconds -- the match as a
    # whole must span at least several minutes across 221+ rallies.
    assert rallies[-1].video_t_end - rallies[0].video_t_start > 60.0


def test_persist_synthetic_match_is_deterministic_in_row_counts_for_same_seed(db):
    """Persisting the same seed twice (into two different matches) should
    produce identical row counts -- proves persistence doesn't introduce
    its own nondeterminism on top of the already-deterministic generator."""
    match_a = _make_match(db)
    match_b = _make_match(db)
    synthetic_a = generate_synthetic_match(seed=55, home_team="Alpha VC", away_team="Beta VC")
    synthetic_b = generate_synthetic_match(seed=55, home_team="Alpha VC", away_team="Beta VC")

    persist_synthetic_match(db, organization_id="org-1", match_id=match_a.id, synthetic=synthetic_a)
    persist_synthetic_match(db, organization_id="org-1", match_id=match_b.id, synthetic=synthetic_b)
    db.commit()

    count_a = db.scalar(
        select(func.count())
        .select_from(Rally)
        .join(MatchSetRow, Rally.set_id == MatchSetRow.id)
        .where(MatchSetRow.match_id == match_a.id)
    )
    count_b = db.scalar(
        select(func.count())
        .select_from(Rally)
        .join(MatchSetRow, Rally.set_id == MatchSetRow.id)
        .where(MatchSetRow.match_id == match_b.id)
    )
    assert count_a == count_b


def test_persist_synthetic_match_links_match_to_its_home_and_away_teams(db):
    """Match.home_team_id/away_team_id must actually get populated -- an
    earlier version only ever wrote match.status to the Match row, so these
    columns (which MatchOut relies on to answer "home" or "away" without
    inferring it from the synthetic JSON blob) shipped permanently null
    despite existing on the model. No test caught this until independent
    architecture review traced it by hand. See TECH_DEBT.md / ADR-004."""
    match = _make_match(db)
    synthetic = generate_synthetic_match(seed=3, home_team="Alpha VC", away_team="Beta VC")

    persist_synthetic_match(db, organization_id="org-1", match_id=match.id, synthetic=synthetic)
    db.commit()

    db.refresh(match)
    assert match.home_team_id is not None
    assert match.away_team_id is not None
    assert match.home_team_id != match.away_team_id

    home_team = db.get(Team, match.home_team_id)
    away_team = db.get(Team, match.away_team_id)
    assert home_team.name == "Alpha VC"
    assert away_team.name == "Beta VC"


def test_persist_synthetic_match_reuses_season_team_player_roster_across_repeated_demo_runs(db):
    """TECH_DEBT.md's now-fixed 'no get-or-create' entry: two separate demo
    generations for the same org + team names must resolve to the same
    Season/Team/Player/Roster rows, not accumulate duplicates -- otherwise
    a team list view would eventually show many duplicate "Alpha VC" rows
    with no way to tell they're meant to be the same team."""
    match_a = _make_match(db)
    match_b = _make_match(db)
    # Different seeds on purpose -- same team names must still dedup even
    # though the two runs' jersey-number assignments differ.
    synthetic_a = generate_synthetic_match(seed=1, home_team="Alpha VC", away_team="Beta VC")
    synthetic_b = generate_synthetic_match(seed=2, home_team="Alpha VC", away_team="Beta VC")

    persist_synthetic_match(db, organization_id="org-1", match_id=match_a.id, synthetic=synthetic_a)
    persist_synthetic_match(db, organization_id="org-1", match_id=match_b.id, synthetic=synthetic_b)
    db.commit()
    db.refresh(match_a)
    db.refresh(match_b)

    # Same physical teams reused, not two "Alpha VC" rows.
    assert match_a.home_team_id == match_b.home_team_id
    assert match_a.away_team_id == match_b.away_team_id
    team_count = db.scalar(select(func.count()).select_from(Team))
    assert team_count == 2  # Alpha VC + Beta VC, not 4

    season_count = db.scalar(select(func.count()).select_from(Season))
    assert season_count == 1  # "Synthetic Demo Season" reused, not duplicated

    player_count = db.scalar(select(func.count()).select_from(Player))
    assert player_count == 14  # 7 players x 2 teams, not 28

    roster_count = db.scalar(select(func.count()).select_from(Roster))
    assert roster_count == 14  # one membership per player, not one per demo run

    # A cross-org demo run with the same team name must NOT dedup against
    # a different tenant's rows -- multi-tenancy isolation applies to
    # get-or-create lookups exactly like every other query in this project.
    match_c = _make_match(db, organization_id="org-2")
    synthetic_c = generate_synthetic_match(seed=1, home_team="Alpha VC", away_team="Beta VC")
    persist_synthetic_match(db, organization_id="org-2", match_id=match_c.id, synthetic=synthetic_c)
    db.commit()

    assert db.scalar(select(func.count()).select_from(Team)) == 4
    assert db.scalar(select(func.count()).select_from(Season)) == 2


def test_persist_synthetic_match_keeps_each_players_original_jersey_number_on_reuse(db):
    """When a Roster membership already exists, a later demo run's freshly
    -randomized jersey_number for the same physical player must NOT
    overwrite the original -- get-or-create means "reuse", not "upsert"."""

    match_a = _make_match(db)
    match_b = _make_match(db)
    synthetic_a = generate_synthetic_match(seed=10, home_team="Alpha VC", away_team="Beta VC")
    synthetic_b = generate_synthetic_match(seed=99, home_team="Alpha VC", away_team="Beta VC")

    persist_synthetic_match(db, organization_id="org-1", match_id=match_a.id, synthetic=synthetic_a)
    db.commit()
    jersey_numbers_after_first_run = {
        (r.team_id, r.player_id): r.jersey_number for r in db.query(Roster).all()
    }

    persist_synthetic_match(db, organization_id="org-1", match_id=match_b.id, synthetic=synthetic_b)
    db.commit()
    jersey_numbers_after_second_run = {
        (r.team_id, r.player_id): r.jersey_number for r in db.query(Roster).all()
    }

    assert jersey_numbers_after_first_run == jersey_numbers_after_second_run
