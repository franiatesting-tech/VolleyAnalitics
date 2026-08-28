import pytest
from conftest import OTHER_ORG_PRINCIPAL
from sqlalchemy import select
from volley_domain.models import JobStatus, ProcessingJob


@pytest.mark.asyncio
async def test_create_and_list_match(client):
    create_resp = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    assert create_resp.status_code == 201
    match = create_resp.json()
    assert match["organization_id"] == "org-1"
    assert match["status"] == "draft"

    list_resp = await client.get("/api/v1/matches")
    assert list_resp.status_code == 200
    matches = list_resp.json()
    assert any(m["id"] == match["id"] for m in matches)


@pytest.mark.asyncio
async def test_matches_are_isolated_by_organization(client, override_principal):
    create_resp = await client.post(
        "/api/v1/matches", json={"home_team": "Org1 Home", "away_team": "Org1 Away"}
    )
    org1_match_id = create_resp.json()["id"]

    # Switch the authenticated principal to a different organization --
    # this is the exact scenario the org-scoping rule in CLAUDE.md exists
    # to prevent a cross-tenant leak on.
    override_principal["value"] = OTHER_ORG_PRINCIPAL

    list_resp = await client.get("/api/v1/matches")
    assert list_resp.json() == []

    get_resp = await client.get(f"/api/v1/matches/{org1_match_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_demo_process_trigger_is_idempotent(client):
    create_resp = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    match_id = create_resp.json()["id"]

    first = await client.post(f"/api/v1/matches/{match_id}/demo-process")
    assert first.status_code == 200
    first_job = first.json()
    assert first_job["status"] == "queued"
    assert first_job["task_name"] == "process_demo_match"

    second = await client.post(f"/api/v1/matches/{match_id}/demo-process")
    assert second.status_code == 200
    second_job = second.json()

    # Same dedup key -> same job row -> never a second job created.
    assert second_job["id"] == first_job["id"]


@pytest.mark.asyncio
async def test_job_status_endpoint_is_org_scoped(client, override_principal, db_engine):
    create_resp = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    match_id = create_resp.json()["id"]
    job_resp = await client.post(f"/api/v1/matches/{match_id}/demo-process")
    job_id = job_resp.json()["id"]

    own_org_resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert own_org_resp.status_code == 200

    override_principal["value"] = OTHER_ORG_PRINCIPAL
    other_org_resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert other_org_resp.status_code == 404


@pytest.mark.asyncio
async def test_result_endpoint_409s_before_completion_and_returns_data_after(client, db_engine):
    create_resp = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    match_id = create_resp.json()["id"]
    await client.post(f"/api/v1/matches/{match_id}/demo-process")

    not_ready = await client.get(f"/api/v1/matches/{match_id}/result")
    assert not_ready.status_code == 409

    # Simulate the worker completing the job (worker-side logic has its own
    # test coverage in services/worker/tests -- this only checks the API's
    # read path once a job is marked completed). Uses the real generator
    # rather than a hand-typed fixture, so this stays honest about the
    # actual SyntheticMatch shape response_model=SyntheticMatch enforces.
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from volley_domain.synthetic import generate_synthetic_match

    synthetic = generate_synthetic_match(seed=1, home_team="Alpha VC", away_team="Beta VC")

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as db:
        job = (
            await db.execute(select(ProcessingJob).where(ProcessingJob.match_id == match_id))
        ).scalar_one()
        job.status = JobStatus.COMPLETED
        job.result_data = synthetic.model_dump(mode="json")
        await db.commit()

    ready = await client.get(f"/api/v1/matches/{match_id}/result")
    assert ready.status_code == 200
    assert ready.json()["home_roster"]["team_name"] == "Alpha VC"
