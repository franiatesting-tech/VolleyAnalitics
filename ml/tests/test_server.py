"""volley_ml.detection.server -- the local inference HTTP contract that
services/worker's detection Celery task depends on. Exercised against a
fake model (not the real RF-DETR checkpoint/torch, which this module's own
`server` extra doesn't even install by default) so this suite runs without
either heavy dependency; the real end-to-end path is covered by manually
running the server against real footage, same as RFDETR_NANO_SMOKE.md's
existing smoke-test precedent for the CLI adapter.
"""

import io
from types import SimpleNamespace

import numpy as np
import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
PILImage = pytest.importorskip("PIL.Image")
PILImageDraw = pytest.importorskip("PIL.ImageDraw")

from volley_ml.detection import server as server_module  # noqa: E402


class _FakeDetections:
    def __init__(self, xyxy, confidence, class_id):
        self.xyxy = np.array(xyxy, dtype=float)
        self.confidence = np.array(confidence, dtype=float)
        self.class_id = np.array(class_id, dtype=int)


class _FakeModel:
    def __init__(self, detections: _FakeDetections):
        self._detections = detections

    def predict(self, source, threshold):
        return self._detections


def _rgb_image_bytes(width: int = 100, height: int = 100, color=(10, 10, 10)) -> bytes:
    image = PILImage.new("RGB", (width, height), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _image_with_ball_patch(
    width: int = 100,
    height: int = 100,
    background=(10, 10, 10),
    bbox: tuple[int, int, int, int] = (50, 50, 60, 60),
    accent_color=(0, 160, 60),
) -> bytes:
    """A background plus a white+accent-color patch at `bbox` -- passes
    ball_plausibility.has_ball_color_pattern's white+accent-fraction gate
    (half white, half a manufacturer accent color), so tests that assert
    an above-threshold ball candidate is returned don't get silently
    rejected by that gate instead of exercising what they actually test."""
    image = PILImage.new("RGB", (width, height), color=background)
    draw = PILImageDraw.Draw(image)
    x1, y1, x2, y2 = bbox
    mid_x = (x1 + x2) // 2
    draw.rectangle([x1, y1, mid_x, y2], fill=(250, 250, 250))
    draw.rectangle([mid_x, y1, x2, y2], fill=accent_color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture()
def client(monkeypatch):
    server_module._get_model.cache_clear()
    return fastapi_testclient.TestClient(server_module.app)


def _stub_model(monkeypatch, detections: _FakeDetections, weights_sha256: str = "f" * 64) -> None:
    loaded = SimpleNamespace(model=_FakeModel(detections), weights_sha256=weights_sha256)
    monkeypatch.setattr(server_module, "_get_model", lambda: loaded)


def test_health_reports_model_identity(client, monkeypatch):
    _stub_model(monkeypatch, _FakeDetections([], [], []))
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["weights_sha256"] == "f" * 64


def test_detect_frame_filters_to_person_class_only(client, monkeypatch):
    # class_id 1 is COCO's person class; 3 is "car" -- must be dropped.
    _stub_model(
        monkeypatch,
        _FakeDetections(
            xyxy=[[10, 10, 40, 90], [5, 5, 20, 20]],
            confidence=[0.9, 0.8],
            class_id=[1, 3],
        ),
    )
    response = client.post(
        "/detect-frame",
        files={"image": ("frame.png", _rgb_image_bytes(), "image/png")},
        data={"threshold": "0.35"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["boxes"]) == 1
    assert body["boxes"][0]["confidence"] == pytest.approx(0.9)
    assert body["balls"] == []


def test_detect_frame_includes_ball_detections(client, monkeypatch):
    # class_id 37 is COCO's "sports ball" class -- verified directly
    # against rfdetr.assets.coco_classes.COCO_CLASSES, not assumed.
    _stub_model(
        monkeypatch,
        _FakeDetections(
            xyxy=[[10, 10, 40, 90], [50, 50, 60, 60]],
            confidence=[0.9, 0.5],
            class_id=[1, 37],
        ),
    )
    response = client.post(
        "/detect-frame",
        files={"image": ("frame.png", _image_with_ball_patch(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["boxes"]) == 1
    assert len(body["balls"]) == 1
    assert body["balls"][0]["confidence"] == pytest.approx(0.5)
    assert body["balls"][0]["x1"] == 50.0


def test_detect_frame_ball_threshold_is_independent_of_person_threshold(client, monkeypatch):
    # A 0.2-confidence ball must pass the default ball_threshold (0.15)
    # even though it would fail the (much higher) default person
    # threshold (0.35) -- a real flying ball is small/blurred and
    # genuinely harder to detect confidently than a person, so it needs
    # its own, more permissive floor.
    _stub_model(
        monkeypatch,
        _FakeDetections(xyxy=[[50, 50, 60, 60]], confidence=[0.2], class_id=[37]),
    )
    response = client.post(
        "/detect-frame",
        files={"image": ("frame.png", _image_with_ball_patch(), "image/png")},
    )
    assert response.status_code == 200
    assert len(response.json()["balls"]) == 1


def test_detect_frame_drops_a_ball_below_ball_threshold(client, monkeypatch):
    _stub_model(
        monkeypatch,
        _FakeDetections(xyxy=[[50, 50, 60, 60]], confidence=[0.1], class_id=[37]),
    )
    response = client.post(
        "/detect-frame",
        files={"image": ("frame.png", _image_with_ball_patch(), "image/png")},
        data={"ball_threshold": "0.15"},
    )
    assert response.status_code == 200
    assert response.json()["balls"] == []


def test_detect_frame_drops_a_ball_candidate_with_no_ball_color_pattern(client, monkeypatch):
    # A shoe or a crowd-area object above the confidence threshold but
    # with none of a real volleyball's white+accent-color pattern (see
    # ball_plausibility.py) -- must still be dropped.
    _stub_model(
        monkeypatch,
        _FakeDetections(xyxy=[[50, 50, 60, 60]], confidence=[0.9], class_id=[37]),
    )
    response = client.post(
        "/detect-frame",
        # Plain solid-color image -- no helper patch drawn at the bbox.
        files={"image": ("frame.png", _rgb_image_bytes(), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["balls"] == []


def test_detect_frame_drops_an_elongated_ball_candidate(client, monkeypatch):
    # Correct ball colors but a shoe-shaped elongated box -- the shape
    # gate must reject it independently of the color gate.
    _stub_model(
        monkeypatch,
        _FakeDetections(xyxy=[[10, 50, 70, 60]], confidence=[0.9], class_id=[37]),
    )
    response = client.post(
        "/detect-frame",
        files={
            "image": (
                "frame.png",
                _image_with_ball_patch(bbox=(10, 50, 70, 60)),
                "image/png",
            )
        },
    )
    assert response.status_code == 200
    assert response.json()["balls"] == []


def test_detect_frame_clamps_boxes_to_image_bounds(client, monkeypatch):
    _stub_model(
        monkeypatch,
        _FakeDetections(
            xyxy=[[-5, -5, 150, 150]],  # image is 100x100 -- must clamp, not reject
            confidence=[0.7],
            class_id=[1],
        ),
    )
    response = client.post(
        "/detect-frame",
        files={"image": ("frame.png", _rgb_image_bytes(width=100, height=100), "image/png")},
    )
    assert response.status_code == 200
    box = response.json()["boxes"][0]
    assert box["x1"] == 0.0
    assert box["y1"] == 0.0
    assert box["x2"] == 100.0
    assert box["y2"] == 100.0


def test_detect_frame_rejects_degenerate_box(client, monkeypatch):
    _stub_model(
        monkeypatch,
        _FakeDetections(
            xyxy=[[50, 50, 50, 90]],  # zero width -- x2 == x1
            confidence=[0.7],
            class_id=[1],
        ),
    )
    response = client.post(
        "/detect-frame",
        files={"image": ("frame.png", _rgb_image_bytes(), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["boxes"] == []


def test_detect_frame_rejects_invalid_threshold(client, monkeypatch):
    _stub_model(monkeypatch, _FakeDetections([], [], []))
    response = client.post(
        "/detect-frame",
        files={"image": ("frame.png", _rgb_image_bytes(), "image/png")},
        data={"threshold": "1.5"},
    )
    assert response.status_code == 422


def test_detect_frame_rejects_undecodable_image(client, monkeypatch):
    _stub_model(monkeypatch, _FakeDetections([], [], []))
    response = client.post(
        "/detect-frame",
        files={"image": ("frame.png", b"not an image", "image/png")},
    )
    assert response.status_code == 422


def test_detect_frame_flags_a_real_jersey_color_outlier(client, monkeypatch):
    # Two yellow team-A boxes, two white team-B boxes (each pair gives the
    # other a same-color neighbor), one visually distinct blue box (no
    # neighbor -- must be flagged), and one tiny distant box that must be
    # excluded from clustering entirely by the on-court-height gate (same
    # as rfdetr_preannotation.py's flag_jersey_color_outliers). Five
    # eligible boxes clears cluster_jersey_colors' min_boxes_to_cluster=4
    # floor -- three would silently skip clustering altogether.
    width, height = 260, 200
    image = PILImage.new("RGB", (width, height), color=(255, 255, 255))
    pixels = image.load()
    for x in range(10, 30):
        for y in range(10, 90):
            pixels[x, y] = (220, 200, 40)  # team A torso, box 0
    for x in range(60, 80):
        for y in range(10, 90):
            pixels[x, y] = (225, 205, 45)  # team A torso, box 1 (same color)
    for x in range(110, 130):
        for y in range(10, 90):
            pixels[x, y] = (20, 30, 200)  # distinct blue torso, box 2 -- outlier
    for x in range(160, 180):
        for y in range(10, 90):
            pixels[x, y] = (235, 90, 210)  # team B torso, box 3
    for x in range(210, 230):
        for y in range(10, 90):
            pixels[x, y] = (230, 95, 215)  # team B torso, box 4 (same color)
    for x in range(250, 255):
        for y in range(10, 15):
            pixels[x, y] = (0, 200, 0)  # tiny distant box, below height gate

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    _stub_model(
        monkeypatch,
        _FakeDetections(
            xyxy=[
                [10, 10, 30, 90],
                [60, 10, 80, 90],
                [110, 10, 130, 90],
                [160, 10, 180, 90],
                [210, 10, 230, 90],
                [250, 10, 255, 15],
            ],
            confidence=[0.9, 0.9, 0.9, 0.9, 0.9, 0.9],
            class_id=[1, 1, 1, 1, 1, 1],
        ),
    )
    response = client.post(
        "/detect-frame",
        files={"image": ("frame.png", buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 200
    boxes = response.json()["boxes"]
    outlier_flags = [box["jersey_color_outlier"] for box in boxes]
    assert outlier_flags == [False, False, True, False, False, False]
