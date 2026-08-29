"""Tests the ontology read endpoints against real persisted data (generated
via the same generate_synthetic_match -> persist_synthetic_match pipeline
the worker uses), not hand-typed fixtures -- proves the whole chain (models
-> persistence -> API -> response_model serialization) actually works
together, not just each piece in isolation."""

import pytest
from conftest import OTHER_ORG_PRINCIPAL
from sqlalchemy.ext.asyncio import async_sessionmaker
from volley_domain.models import Match
from volley_domain.synthetic.generator import generate_synthetic_match
from volley_domain.synthetic.persistence import persist_synthetic_match


async def _seed_persisted_match(db_engine, organization_id: str = "org-1", seed: int = 42) -> str:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as db:
        match = Match(
            organization_id=organization_id,
            home_team="Alpha VC",
            away_team="Beta VC",
            created_by_user_id="user-1",
        )
        db.add(match)
        await db.flush()
        match_id = match.id

        # persist_synthetic_match is written for a sync Session; the test
        # fixtures elsewhere in this suite use SQLite via an async engine,
        # so this uses the sync SQLAlchemy API against the same connection
        # via run_sync, matching how Alembic's migrations do sync work
        # against an async-configured engine.
        def _persist(sync_session):
            synthetic = generate_synthetic_match(
                seed=seed, home_team="Alpha VC", away_team="Beta VC"
            )
            persist_synthetic_match(
                sync_session,
                organization_id=organization_id,
                match_id=match_id,
                synthetic=synthetic,
            )

        await db.run_sync(_persist)
        await db.commit()
    return match_id


@pytest.mark.asyncio
async def test_list_sets_returns_persisted_sets(client, db_engine):
    match_id = await _seed_persisted_match(db_engine)

    response = await client.get(f"/api/v1/matches/{match_id}/sets")
    assert response.status_code == 200
    sets = response.json()
    assert len(sets) >= 3  # a completed match is at least 3 sets
    assert sets[0]["index"] == 0


@pytest.mark.asyncio
async def test_list_rallies_returns_rallies_across_all_sets(client, db_engine):
    match_id = await _seed_persisted_match(db_engine)

    response = await client.get(f"/api/v1/matches/{match_id}/rallies")
    assert response.status_code == 200
    rallies = response.json()
    assert len(rallies) > 0
    assert all("serving_team_id" in r for r in rallies)


@pytest.mark.asyncio
async def test_list_rally_actions_returns_actions_with_outcomes(client, db_engine):
    match_id = await _seed_persisted_match(db_engine)

    rallies_response = await client.get(f"/api/v1/matches/{match_id}/rallies")
    first_rally_id = rallies_response.json()[0]["id"]

    response = await client.get(f"/api/v1/rallies/{first_rally_id}/actions")
    assert response.status_code == 200
    actions = response.json()
    assert len(actions) > 0
    assert actions[0]["outcome"] is not None or len(actions) > 1  # at least some carry an outcome
    assert any(a["outcome"] is not None for a in actions)


@pytest.mark.asyncio
async def test_match_statistics_endpoint_returns_computed_stats(client, db_engine):
    match_id = await _seed_persisted_match(db_engine)

    response = await client.get(f"/api/v1/matches/{match_id}/statistics")
    assert response.status_code == 200
    stats = response.json()
    assert stats["formula_version"]
    assert len(stats["serve"]) == 2  # both teams served
    assert len(stats["sideout_breakpoint"]) == 2


@pytest.mark.asyncio
async def test_ontology_endpoints_are_org_scoped(client, db_engine, override_principal):
    match_id = await _seed_persisted_match(db_engine, organization_id="org-1")

    override_principal["value"] = OTHER_ORG_PRINCIPAL
    sets_response = await client.get(f"/api/v1/matches/{match_id}/sets")
    assert sets_response.status_code == 404

    rallies_response = await client.get(f"/api/v1/matches/{match_id}/rallies")
    assert rallies_response.status_code == 404

    stats_response = await client.get(f"/api/v1/matches/{match_id}/statistics")
    assert stats_response.status_code == 404


@pytest.mark.asyncio
async def test_rally_actions_endpoint_is_org_scoped_via_match_join(
    client, db_engine, override_principal
):
    """The rally-actions route resolves org scope by joining Rally -> Set ->
    Match, not from a column on Rally itself -- this is the specific join
    chain that must be correct."""
    match_id = await _seed_persisted_match(db_engine, organization_id="org-1")
    rallies_response = await client.get(f"/api/v1/matches/{match_id}/rallies")
    first_rally_id = rallies_response.json()[0]["id"]

    override_principal["value"] = OTHER_ORG_PRINCIPAL
    response = await client.get(f"/api/v1/rallies/{first_rally_id}/actions")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_sets_404s_for_nonexistent_match(client):
    response = await client.get("/api/v1/matches/does-not-exist/sets")
    assert response.status_code == 404
