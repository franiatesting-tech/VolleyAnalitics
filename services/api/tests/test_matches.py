import pytest
from sqlalchemy import select
from volley_api.core.auth import Principal
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
async def test_member_can_read_but_cannot_create_matches(client, override_principal):
    override_principal["value"] = Principal(
        user_id="member-1", organization_id="org-1", role="member"
    )
    assert (await client.get("/api/v1/matches")).status_code == 200
    response = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_matches_are_isolated_by_organization(
    client, override_principal, other_org_principal
):
    create_resp = await client.post(
        "/api/v1/matches", json={"home_team": "Org1 Home", "away_team": "Org1 Away"}
    )
    org1_match_id = create_resp.json()["id"]

    # Switch the authenticated principal to a different organization --
    # this is the exact scenario the org-scoping rule in CLAUDE.md exists
    # to prevent a cross-tenant leak on.
    override_principal["value"] = other_org_principal

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
async def test_member_cannot_trigger_processing(client, override_principal):
    create_resp = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    match_id = create_resp.json()["id"]
    override_principal["value"] = Principal(
        user_id="member-1", organization_id="org-1", role="member"
    )

    response = await client.post(f"/api/v1/matches/{match_id}/demo-process")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_job_status_endpoint_is_org_scoped(
    client, override_principal, other_org_principal, db_engine
):
    create_resp = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    match_id = create_resp.json()["id"]
    job_resp = await client.post(f"/api/v1/matches/{match_id}/demo-process")
    job_id = job_resp.json()["id"]

    own_org_resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert own_org_resp.status_code == 200

    override_principal["value"] = other_org_principal
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


@pytest.mark.asyncio
async def test_delete_match_removes_it(client):
    create_resp = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    match_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/matches/{match_id}")
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/matches/{match_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_match_cascades_to_its_processing_job(client, db_engine):
    create_resp = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    match_id = create_resp.json()["id"]
    await client.post(f"/api/v1/matches/{match_id}/demo-process")

    delete_resp = await client.delete(f"/api/v1/matches/{match_id}")
    assert delete_resp.status_code == 204

    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as db:
        remaining = (
            (await db.execute(select(ProcessingJob).where(ProcessingJob.match_id == match_id)))
            .scalars()
            .all()
        )
        assert remaining == []


@pytest.mark.asyncio
async def test_delete_match_unlinks_but_does_not_delete_its_video(client, db_engine):
    create_resp = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    match_id = create_resp.json()["id"]
    video_resp = await client.post(
        "/api/v1/videos",
        json={"filename": "match.mp4", "content_type": "video/mp4", "match_id": match_id},
    )
    video_id = video_resp.json()["video_id"]

    delete_resp = await client.delete(f"/api/v1/matches/{match_id}")
    assert delete_resp.status_code == 204

    get_video_resp = await client.get(f"/api/v1/videos/{video_id}")
    assert get_video_resp.status_code == 200
    assert get_video_resp.json()["match_id"] is None


@pytest.mark.asyncio
async def test_member_cannot_delete_a_match(client, override_principal):
    create_resp = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    match_id = create_resp.json()["id"]

    override_principal["value"] = Principal(
        user_id="member-1", organization_id="org-1", role="member"
    )
    delete_resp = await client.delete(f"/api/v1/matches/{match_id}")
    assert delete_resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_match_is_org_scoped(client, override_principal, other_org_principal):
    create_resp = await client.post(
        "/api/v1/matches", json={"home_team": "Alpha VC", "away_team": "Beta VC"}
    )
    match_id = create_resp.json()["id"]

    override_principal["value"] = other_org_principal
    delete_resp = await client.delete(f"/api/v1/matches/{match_id}")
    assert delete_resp.status_code == 404
