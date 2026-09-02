"""Video ingest endpoint tests. `create_video_upload` + `local_upload` are
exercised against the real LocalFilesystemStorageAdapter (see conftest.py's
LOCAL_STORAGE_DIR override) -- the signed-URL round trip is real, not
mocked. `complete_video_upload`'s Celery enqueue is stubbed the same way
matches.py's demo-process trigger already is (see conftest.py's client
fixture) -- worker-side ingest logic has its own coverage in
services/worker/tests.
"""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from volley_api.core.auth import Principal


def _extract_token_and_expiry(upload_url: str) -> tuple[str, str]:
    query = parse_qs(urlparse(upload_url).query)
    return query["token"][0], query["expires_at"][0]


@pytest.mark.asyncio
async def test_create_video_upload_issues_a_signed_target(client):
    resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["video_id"]
    assert body["upload"]["method"] == "PUT"
    assert "token=" in body["upload"]["url"]
    assert body["upload"]["headers"]["Content-Type"] == "video/mp4"


@pytest.mark.asyncio
async def test_member_cannot_create_video_upload(client, override_principal):
    override_principal["value"] = Principal(
        user_id="member-1", organization_id="org-1", role="member"
    )
    response = await client.post(
        "/api/v1/videos",
        json={"filename": "match.mp4", "content_type": "video/mp4", "size_bytes": 128},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_video_upload_rejects_declared_oversize_file(client):
    response = await client.post(
        "/api/v1/videos",
        json={
            "filename": "match.mp4",
            "content_type": "video/mp4",
            "size_bytes": 20 * 1024 * 1024 * 1024 + 1,
        },
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_local_upload_stream_enforces_limit(client, monkeypatch):
    limits = SimpleNamespace(max_video_upload_bytes=4, local_upload_max_bytes=4)
    monkeypatch.setattr("volley_api.api.routes.videos.get_settings", lambda: limits)
    create_resp = await client.post(
        "/api/v1/videos",
        json={"filename": "match.mp4", "content_type": "video/mp4", "size_bytes": 4},
    )
    parsed = urlparse(create_resp.json()["upload"]["url"])

    response = await client.put(f"{parsed.path}?{parsed.query}", content=b"12345")

    assert response.status_code == 413


@pytest.mark.asyncio
async def test_create_video_upload_rejects_unknown_match_id(client):
    resp = await client.post(
        "/api/v1/videos",
        json={"filename": "match.mp4", "content_type": "video/mp4", "match_id": "does-not-exist"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_full_upload_and_complete_flow(client):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    upload_url = create_resp.json()["upload"]["url"]

    # The signed URL is absolute (http://test/api/v1/storage/...) -- strip
    # the base so httpx's test transport (bound to "http://test") resolves it.
    parsed = urlparse(upload_url)
    relative_url = f"{parsed.path}?{parsed.query}"

    put_resp = await client.put(relative_url, content=b"fake mp4 bytes for this test")
    assert put_resp.status_code == 200

    complete_resp = await client.post(f"/api/v1/videos/{video_id}/complete-upload")
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "validating"

    get_resp = await client.get(f"/api/v1/videos/{video_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "validating"


@pytest.mark.asyncio
async def test_complete_upload_is_idempotent(client):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    upload_url = create_resp.json()["upload"]["url"]
    parsed = urlparse(upload_url)
    await client.put(f"{parsed.path}?{parsed.query}", content=b"bytes")

    first = await client.post(f"/api/v1/videos/{video_id}/complete-upload")
    second = await client.post(f"/api/v1/videos/{video_id}/complete-upload")
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "validating"  # not re-enqueued into uploaded/failed


@pytest.mark.asyncio
async def test_complete_upload_without_original_asset_conflicts(client, db_engine):
    # A video row with no matching VideoAsset(kind=ORIGINAL) can't happen
    # through the normal create_video_upload path (both are created
    # together), but this guards the invariant explicitly rather than
    # trusting it silently.
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from volley_domain.ontology import VideoAsset

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as db:
        await db.execute(delete(VideoAsset).where(VideoAsset.video_id == video_id))
        await db.commit()

    resp = await client.post(f"/api/v1/videos/{video_id}/complete-upload")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_local_upload_rejects_invalid_token(client):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    upload_url = create_resp.json()["upload"]["url"]
    parsed = urlparse(upload_url)
    query = parse_qs(parsed.query)
    bad_url = f"{parsed.path}?token=not-the-real-token&expires_at={query['expires_at'][0]}"

    resp = await client.put(bad_url, content=b"bytes")
    assert resp.status_code == 403


async def _mark_video_ready(db_engine, video_id: str) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from volley_domain.ontology import Video, VideoStatus

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as db:
        video = await db.get(Video, video_id)
        video.status = VideoStatus.READY
        await db.commit()


@pytest.mark.asyncio
async def test_playback_url_requires_the_video_to_be_ready(client):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]

    resp = await client.get(f"/api/v1/videos/{video_id}/playback-url")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_playback_url_issues_a_working_signed_download_for_a_ready_video(client, db_engine):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    upload_url = create_resp.json()["upload"]["url"]
    upload_parsed = urlparse(upload_url)
    put_resp = await client.put(
        f"{upload_parsed.path}?{upload_parsed.query}", content=b"fake mp4 bytes"
    )
    assert put_resp.status_code == 200

    await _mark_video_ready(db_engine, video_id)

    playback_resp = await client.get(f"/api/v1/videos/{video_id}/playback-url")
    assert playback_resp.status_code == 200
    playback_url = playback_resp.json()["playback"]["url"]
    assert "token=" in playback_url

    download_parsed = urlparse(playback_url)
    download_resp = await client.get(f"{download_parsed.path}?{download_parsed.query}")
    assert download_resp.status_code == 200
    assert download_resp.content == b"fake mp4 bytes"


@pytest.mark.asyncio
async def test_local_download_rejects_invalid_token(client, db_engine):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    upload_url = create_resp.json()["upload"]["url"]
    upload_parsed = urlparse(upload_url)
    await client.put(f"{upload_parsed.path}?{upload_parsed.query}", content=b"bytes")
    await _mark_video_ready(db_engine, video_id)

    playback_resp = await client.get(f"/api/v1/videos/{video_id}/playback-url")
    playback_parsed = urlparse(playback_resp.json()["playback"]["url"])
    query = parse_qs(playback_parsed.query)
    bad_url = f"{playback_parsed.path}?token=not-the-real-token&expires_at={query['expires_at'][0]}"

    resp = await client.get(bad_url)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_an_upload_token_cannot_be_used_to_download(client, db_engine):
    """A signed upload URL (write) must never double as a valid download
    (read) token for the same key -- the two token spaces are
    cryptographically disjoint, not just conventionally separated by URL
    path (see LocalFilesystemStorageAdapter._token_for's docstring)."""
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    upload_url = create_resp.json()["upload"]["url"]
    upload_parsed = urlparse(upload_url)
    await client.put(f"{upload_parsed.path}?{upload_parsed.query}", content=b"bytes")
    await _mark_video_ready(db_engine, video_id)

    upload_token, upload_expires_at = _extract_token_and_expiry(upload_url)
    playback_resp = await client.get(f"/api/v1/videos/{video_id}/playback-url")
    download_key_path = urlparse(playback_resp.json()["playback"]["url"]).path

    resp = await client.get(
        f"{download_key_path}?token={upload_token}&expires_at={upload_expires_at}"
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_detect_requires_the_video_to_be_ready(client):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]

    resp = await client.post(f"/api/v1/videos/{video_id}/detect")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_detect_enqueues_and_is_idempotent(client, db_engine):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    await _mark_video_ready(db_engine, video_id)

    first = await client.post(f"/api/v1/videos/{video_id}/detect")
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "queued"
    pipeline_run_id = body["pipeline_run_id"]

    # A second trigger while still queued must reuse the same run, not
    # double-enqueue -- same idempotency rule as matches.py's demo-process
    # trigger and complete_video_upload.
    second = await client.post(f"/api/v1/videos/{video_id}/detect")
    assert second.status_code == 200
    assert second.json()["pipeline_run_id"] == pipeline_run_id


@pytest.mark.asyncio
async def test_detect_threads_max_duration_seconds_through_to_the_celery_task(
    client, db_engine, monkeypatch
):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    await _mark_video_ready(db_engine, video_id)

    captured: dict = {}

    class _CapturingCeleryClient:
        def send_task(self, name, kwargs):
            captured["name"] = name
            captured["kwargs"] = kwargs

            class _Result:
                id = "fake-task-id"

            return _Result()

    monkeypatch.setattr("volley_api.core.tasks.get_celery_client", lambda: _CapturingCeleryClient())

    resp = await client.post(
        f"/api/v1/videos/{video_id}/detect", json={"max_duration_seconds": 1200.0}
    )
    assert resp.status_code == 200
    assert captured["kwargs"]["max_duration_seconds"] == 1200.0


@pytest.mark.asyncio
async def test_detect_threads_start_offset_seconds_through_to_the_celery_task(
    client, db_engine, monkeypatch
):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    await _mark_video_ready(db_engine, video_id)

    captured: dict = {}

    class _CapturingCeleryClient:
        def send_task(self, name, kwargs):
            captured["name"] = name
            captured["kwargs"] = kwargs

            class _Result:
                id = "fake-task-id"

            return _Result()

    monkeypatch.setattr("volley_api.core.tasks.get_celery_client", lambda: _CapturingCeleryClient())

    resp = await client.post(
        f"/api/v1/videos/{video_id}/detect", json={"start_offset_seconds": 412.0}
    )
    assert resp.status_code == 200
    assert captured["kwargs"]["start_offset_seconds"] == 412.0


@pytest.mark.asyncio
async def test_detect_threads_sample_fps_through_to_the_celery_task(client, db_engine, monkeypatch):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    await _mark_video_ready(db_engine, video_id)

    captured: dict = {}

    class _CapturingCeleryClient:
        def send_task(self, name, kwargs):
            captured["name"] = name
            captured["kwargs"] = kwargs

            class _Result:
                id = "fake-task-id"

            return _Result()

    monkeypatch.setattr("volley_api.core.tasks.get_celery_client", lambda: _CapturingCeleryClient())

    resp = await client.post(f"/api/v1/videos/{video_id}/detect", json={"sample_fps": 10.0})
    assert resp.status_code == 200
    assert captured["kwargs"]["sample_fps"] == 10.0


@pytest.mark.asyncio
async def test_detect_member_cannot_trigger(client, override_principal, db_engine):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    await _mark_video_ready(db_engine, video_id)

    from volley_api.core.auth import Principal

    override_principal["value"] = Principal(
        user_id="member-1", organization_id="org-1", role="member"
    )
    resp = await client.post(f"/api/v1/videos/{video_id}/detect")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_detection_status_is_honest_when_never_triggered(client, db_engine):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    await _mark_video_ready(db_engine, video_id)

    resp = await client.get(f"/api/v1/videos/{video_id}/detection-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "pipeline_run_id": None,
        "status": None,
        "model_version": None,
        "sample_fps": None,
        "frames_detected": 0,
        "frames_total": None,
        "error": None,
    }


@pytest.mark.asyncio
async def test_detection_status_reflects_a_queued_run(client, db_engine):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    await _mark_video_ready(db_engine, video_id)

    trigger_resp = await client.post(f"/api/v1/videos/{video_id}/detect")
    pipeline_run_id = trigger_resp.json()["pipeline_run_id"]

    resp = await client.get(f"/api/v1/videos/{video_id}/detection-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pipeline_run_id"] == pipeline_run_id
    assert body["status"] == "queued"
    assert body["frames_detected"] == 0


@pytest.mark.asyncio
async def test_detections_are_empty_until_a_run_completes(client, db_engine):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    await _mark_video_ready(db_engine, video_id)

    # Never triggered at all.
    resp = await client.get(f"/api/v1/videos/{video_id}/detections")
    assert resp.status_code == 200
    assert resp.json() == []

    # Triggered but still queued -- not completed yet.
    await client.post(f"/api/v1/videos/{video_id}/detect")
    resp = await client.get(f"/api/v1/videos/{video_id}/detections")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_detections_returns_real_boxes_for_a_completed_run(client, db_engine):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    await _mark_video_ready(db_engine, video_id)

    trigger_resp = await client.post(f"/api/v1/videos/{video_id}/detect")
    pipeline_run_id = trigger_resp.json()["pipeline_run_id"]

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from volley_domain.ontology import (
        ModelRun,
        ModelRunStage,
        PipelineRun,
        PipelineRunStatus,
        VideoDetectionFrame,
    )

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as db:
        pipeline_run = await db.get(PipelineRun, pipeline_run_id)
        assert pipeline_run is not None
        pipeline_run.status = PipelineRunStatus.COMPLETED
        model_run = ModelRun(
            pipeline_run_id=pipeline_run_id,
            stage=ModelRunStage.DETECTION,
            model_version="rfdetr-1.9.4-nano-coco-smoke",
            weights_hash="f" * 64,
            metrics={"base_sample_fps": 0.5, "threshold": 0.35, "frames_total": 1},
        )
        db.add(model_run)
        await db.flush()
        db.add(
            VideoDetectionFrame(
                video_id=video_id,
                model_run_id=model_run.id,
                frame_index=1,
                timestamp_seconds=0.0,
                detections=[
                    {
                        "candidate_id": "box-0",
                        "bbox": {"x": 0.1, "y": 0.2, "width": 0.05, "height": 0.3},
                        "confidence": 0.8,
                        "jersey_color_outlier": False,
                    }
                ],
                ball_detections=[
                    {
                        "candidate_id": "ball-0",
                        "bbox": {"x": 0.5, "y": 0.4, "width": 0.02, "height": 0.02},
                        "confidence": 0.3,
                    }
                ],
            )
        )
        await db.commit()

    status_resp = await client.get(f"/api/v1/videos/{video_id}/detection-status")
    assert status_resp.json()["model_version"] == "rfdetr-1.9.4-nano-coco-smoke"
    assert status_resp.json()["sample_fps"] == 0.5
    assert status_resp.json()["frames_detected"] == 1
    assert status_resp.json()["frames_total"] == 1

    detections_resp = await client.get(f"/api/v1/videos/{video_id}/detections")
    assert detections_resp.status_code == 200
    frames = detections_resp.json()
    assert len(frames) == 1
    assert frames[0]["frame_index"] == 1
    assert frames[0]["detections"][0]["confidence"] == pytest.approx(0.8)
    assert frames[0]["balls"][0]["confidence"] == pytest.approx(0.3)
    assert frames[0]["balls"][0]["bbox"]["x"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_detections_are_isolated_by_organization(
    client, override_principal, other_org_principal, db_engine
):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    await _mark_video_ready(db_engine, video_id)

    override_principal["value"] = other_org_principal
    resp = await client.get(f"/api/v1/videos/{video_id}/detection-status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_videos_are_isolated_by_organization(client, override_principal, other_org_principal):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]

    override_principal["value"] = other_org_principal

    list_resp = await client.get("/api/v1/videos")
    assert list_resp.json() == []

    get_resp = await client.get(f"/api/v1/videos/{video_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_unknown_video_404s(client):
    resp = await client.get("/api/v1/videos/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_video_removes_it_and_its_storage_object(client):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    upload_url = create_resp.json()["upload"]["url"]
    upload_parsed = urlparse(upload_url)
    await client.put(f"{upload_parsed.path}?{upload_parsed.query}", content=b"fake mp4 bytes")

    delete_resp = await client.delete(f"/api/v1/videos/{video_id}")
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/videos/{video_id}")
    assert get_resp.status_code == 404

    # The uploaded object itself is gone from storage too, not just the DB
    # row -- checked directly against the real adapter (same one the route
    # itself uses), not just inferred from the DB row's absence.
    from volley_api.core.storage import get_storage_adapter

    storage_key = f"org-1/videos/{video_id}/original/match.mp4"
    assert not get_storage_adapter().object_exists(storage_key)


@pytest.mark.asyncio
async def test_delete_video_cascades_to_its_detection_data(client, db_engine):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    await _mark_video_ready(db_engine, video_id)
    trigger_resp = await client.post(f"/api/v1/videos/{video_id}/detect")
    pipeline_run_id = trigger_resp.json()["pipeline_run_id"]

    delete_resp = await client.delete(f"/api/v1/videos/{video_id}")
    assert delete_resp.status_code == 204

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from volley_domain.ontology import PipelineRun

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as db:
        assert await db.get(PipelineRun, pipeline_run_id) is None


@pytest.mark.asyncio
async def test_member_cannot_delete_a_video(client, override_principal):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]

    from volley_api.core.auth import Principal

    override_principal["value"] = Principal(
        user_id="member-1", organization_id="org-1", role="member"
    )
    delete_resp = await client.delete(f"/api/v1/videos/{video_id}")
    assert delete_resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_video_is_org_scoped(client, override_principal, other_org_principal):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]

    override_principal["value"] = other_org_principal
    delete_resp = await client.delete(f"/api/v1/videos/{video_id}")
    assert delete_resp.status_code == 404


def _exact_scale_corner_keypoints() -> list[dict]:
    """Pixel (0,0)-(900,1800) maps to court (0,0)-(9,18) meters by a pure
    /100 scale -- an exact 4-point fit (0 degrees of freedom left over), so
    the recovered homography's reprojection error against these same 4
    points should be ~0, a hand-verifiable expectation rather than a
    number that has to be trusted from the algorithm itself."""
    return [
        {"keypoint_name": "near_baseline_left", "x_pixel": 0.0, "y_pixel": 0.0},
        {"keypoint_name": "near_baseline_right", "x_pixel": 900.0, "y_pixel": 0.0},
        {"keypoint_name": "far_baseline_left", "x_pixel": 0.0, "y_pixel": 1800.0},
        {"keypoint_name": "far_baseline_right", "x_pixel": 900.0, "y_pixel": 1800.0},
    ]


async def _create_ready_video(client, db_engine) -> str:
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]
    await _mark_video_ready(db_engine, video_id)
    return video_id


@pytest.mark.asyncio
async def test_court_calibration_requires_the_video_to_be_ready(client):
    create_resp = await client.post(
        "/api/v1/videos", json={"filename": "match.mp4", "content_type": "video/mp4"}
    )
    video_id = create_resp.json()["video_id"]

    resp = await client.post(
        f"/api/v1/videos/{video_id}/court-calibration",
        json={
            "image_width": 900,
            "image_height": 1800,
            "keypoints": _exact_scale_corner_keypoints(),
        },
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_court_calibration_computes_a_near_zero_reprojection_error_for_an_exact_fit(
    client, db_engine
):
    video_id = await _create_ready_video(client, db_engine)

    resp = await client.post(
        f"/api/v1/videos/{video_id}/court-calibration",
        json={
            "image_width": 900,
            "image_height": 1800,
            "keypoints": _exact_scale_corner_keypoints(),
            "net_height_m": 2.43,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["method"] == "manual"
    assert body["reprojection_error_px"] == pytest.approx(0.0, abs=1e-6)
    assert len(body["homography_matrix"]) == 9
    assert body["net_height_m"] == pytest.approx(2.43)
    assert body["court_width_m"] == pytest.approx(9.0)
    assert body["court_length_m"] == pytest.approx(18.0)
    assert body["created_by_user_id"] == "user-1"


@pytest.mark.asyncio
async def test_create_court_calibration_zone_mirror_x_is_optional_and_persisted(client, db_engine):
    video_id = await _create_ready_video(client, db_engine)

    # Omitted entirely -- stays None, never guessed.
    resp = await client.post(
        f"/api/v1/videos/{video_id}/court-calibration",
        json={
            "image_width": 900,
            "image_height": 1800,
            "keypoints": _exact_scale_corner_keypoints(),
        },
    )
    assert resp.status_code == 201
    assert resp.json()["zone_mirror_x"] is None

    # Explicitly set -- persisted and returned.
    resp = await client.post(
        f"/api/v1/videos/{video_id}/court-calibration",
        json={
            "image_width": 900,
            "image_height": 1800,
            "keypoints": _exact_scale_corner_keypoints(),
            "zone_mirror_x": True,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["zone_mirror_x"] is True

    get_resp = await client.get(f"/api/v1/videos/{video_id}/court-calibration")
    assert get_resp.json()["zone_mirror_x"] is True


@pytest.mark.asyncio
async def test_create_court_calibration_rejects_collinear_keypoints(client, db_engine):
    video_id = await _create_ready_video(client, db_engine)

    collinear = [
        {"keypoint_name": "near_baseline_left", "x_pixel": 0.0, "y_pixel": 0.0},
        {"keypoint_name": "near_baseline_right", "x_pixel": 100.0, "y_pixel": 0.0},
        {"keypoint_name": "near_attack_line_left", "x_pixel": 200.0, "y_pixel": 0.0},
        {"keypoint_name": "near_attack_line_right", "x_pixel": 300.0, "y_pixel": 0.0},
    ]
    resp = await client.post(
        f"/api/v1/videos/{video_id}/court-calibration",
        json={"image_width": 900, "image_height": 1800, "keypoints": collinear},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_court_calibration_rejects_fewer_than_four_visible_keypoints(
    client, db_engine
):
    video_id = await _create_ready_video(client, db_engine)

    three_visible = _exact_scale_corner_keypoints()[:3]
    resp = await client.post(
        f"/api/v1/videos/{video_id}/court-calibration",
        json={"image_width": 900, "image_height": 1800, "keypoints": three_visible},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_court_calibration_supersedes_the_previous_one(client, db_engine):
    video_id = await _create_ready_video(client, db_engine)

    first_resp = await client.post(
        f"/api/v1/videos/{video_id}/court-calibration",
        json={
            "image_width": 900,
            "image_height": 1800,
            "keypoints": _exact_scale_corner_keypoints(),
        },
    )
    first_id = first_resp.json()["id"]

    second_resp = await client.post(
        f"/api/v1/videos/{video_id}/court-calibration",
        json={
            "image_width": 900,
            "image_height": 1800,
            "keypoints": _exact_scale_corner_keypoints(),
        },
    )
    assert second_resp.status_code == 201
    second_id = second_resp.json()["id"]
    assert second_id != first_id

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from volley_domain.ontology import CourtCalibration

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as db:
        first = await db.get(CourtCalibration, first_id)
        assert first.superseded_at is not None
        second = await db.get(CourtCalibration, second_id)
        assert second.superseded_at is None

    get_resp = await client.get(f"/api/v1/videos/{video_id}/court-calibration")
    assert get_resp.json()["id"] == second_id


@pytest.mark.asyncio
async def test_get_court_calibration_is_honest_when_none_exists(client, db_engine):
    video_id = await _create_ready_video(client, db_engine)

    resp = await client.get(f"/api/v1/videos/{video_id}/court-calibration")
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_preview_court_calibration_does_not_persist_anything(client, db_engine):
    video_id = await _create_ready_video(client, db_engine)

    preview_resp = await client.post(
        f"/api/v1/videos/{video_id}/court-calibration/preview",
        json={
            "image_width": 900,
            "image_height": 1800,
            "keypoints": _exact_scale_corner_keypoints(),
        },
    )
    assert preview_resp.status_code == 200
    assert preview_resp.json()["reprojection_error_px"] == pytest.approx(0.0, abs=1e-6)

    get_resp = await client.get(f"/api/v1/videos/{video_id}/court-calibration")
    assert get_resp.json() is None


@pytest.mark.asyncio
async def test_court_calibration_member_cannot_create(client, override_principal, db_engine):
    video_id = await _create_ready_video(client, db_engine)

    from volley_api.core.auth import Principal

    override_principal["value"] = Principal(
        user_id="member-1", organization_id="org-1", role="member"
    )
    resp = await client.post(
        f"/api/v1/videos/{video_id}/court-calibration",
        json={
            "image_width": 900,
            "image_height": 1800,
            "keypoints": _exact_scale_corner_keypoints(),
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_court_calibration_is_org_scoped(
    client, override_principal, other_org_principal, db_engine
):
    video_id = await _create_ready_video(client, db_engine)

    override_principal["value"] = other_org_principal
    resp = await client.post(
        f"/api/v1/videos/{video_id}/court-calibration",
        json={
            "image_width": 900,
            "image_height": 1800,
            "keypoints": _exact_scale_corner_keypoints(),
        },
    )
    assert resp.status_code == 404

    get_resp = await client.get(f"/api/v1/videos/{video_id}/court-calibration")
    assert get_resp.status_code == 404
