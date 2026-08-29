"""Verifies persist_synthetic_match actually writes a coherent ontology
graph against a real (SQLite) database -- this is what pays down the
"synthetic match stored as a JSON blob" tech debt entry."""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from volley_domain.base import Base
from volley_domain.models import Match, MatchStatus
from volley_domain.ontology import Action, ModelRun, Outcome, Phase, Rally
from volley_domain.ontology import MatchSet as MatchSetRow
from volley_domain.synthetic.generator import generate_synthetic_match
from volley_domain.synthetic.persistence import persist_synthetic_match


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_match(db: Session) -> Match:
    match = Match(
        organization_id="org-1",
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
