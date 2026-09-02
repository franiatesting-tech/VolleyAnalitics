from datetime import UTC, datetime

import numpy as np
import pytest
from volley_domain.annotation import BoundingBox, FrameRef
from volley_domain.preannotation import PlayerTrackPreannotation, PredictionProvenance

from volley_ml.detection.rfdetr_preannotation import (
    SmokeFrame,
    SmokeRunConfig,
    config_sha256,
    detections_to_preannotations,
    flag_jersey_color_outliers,
)

# Pillow is only ever pulled in by the optional `inference` extra (it rides
# in as rfdetr's own dependency, see pyproject.toml) -- the base `ml`
# install (numpy/pydantic/volley-domain only) deliberately stays light, so
# this test-only import must not break collection of the whole module for
# anyone running the default (non-inference) suite.
Image = pytest.importorskip("PIL.Image")


def _provenance() -> PredictionProvenance:
    return PredictionProvenance(
        organization_id="org-1",
        video_id="video-1",
        video_hash="a" * 64,
        pipeline_run_id="pipeline-1",
        model_run_id="model-1",
        stage="player_detection_preannotation",
        model_family="RF-DETR",
        model_version="nano",
        weights_sha256="b" * 64,
        config_sha256="c" * 64,
        training_dataset_version="coco",
        code_commit="abcdef1",
        source_sha256="d" * 64,
        created_at=datetime.now(UTC),
    )


def _frame() -> SmokeFrame:
    return SmokeFrame(
        image_path="frame.jpg",
        organization_id="org-1",
        video_id="video-1",
        video_hash="a" * 64,
        frame_index=1500,
        timestamp_seconds=30,
        image_width=1280,
        image_height=720,
        sample_role="active_play",
    )


def test_adapter_filters_non_person_and_normalizes_box():
    results = detections_to_preannotations(
        xyxy=[[128, 72, 384, 432], [10, 10, 100, 100]],
        confidences=[0.9, 0.99],
        class_ids=[1, 37],
        frame=_frame(),
        provenance=_provenance(),
    )
    assert len(results) == 1
    assert results[0].bbox.model_dump() == pytest.approx(
        {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.5}
    )
    assert results[0].person_role is None
    assert results[0].track_id is None


def test_adapter_clips_boxes_to_frame_and_drops_degenerate_boxes():
    results = detections_to_preannotations(
        xyxy=[[-10, -20, 1300, 800], [100, 100, 90, 90]],
        confidences=[0.8, 0.7],
        class_ids=[1, 1],
        frame=_frame(),
        provenance=_provenance(),
    )
    assert len(results) == 1
    assert results[0].bbox.model_dump() == pytest.approx(
        {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    )


def _track(candidate_id: str, box: BoundingBox) -> PlayerTrackPreannotation:
    return PlayerTrackPreannotation(
        candidate_id=candidate_id,
        provenance=_provenance(),
        frame=FrameRef(frame_index=1500, timestamp_seconds=30),
        bbox=box,
        confidence=0.8,
    )


def test_flag_jersey_color_outliers_flags_a_distinctly_colored_box():
    """End-to-end through the real function this module wires into
    run_smoke_preannotation: a synthetic frame with two same-colored
    "teams" and one distinctly colored box must flag only that one."""
    width, height = 200, 200
    image = Image.new("RGB", (width, height), (0, 0, 0))
    pixels = np.array(image)
    # Six normalized boxes, each 20x100px, torso band roughly y in [25,55]%.
    boxes = {
        "yellow-1": ((0.02, 0.0, 0.12, 0.5), (230, 220, 40)),
        "yellow-2": ((0.14, 0.0, 0.24, 0.5), (225, 215, 35)),
        "yellow-3": ((0.26, 0.0, 0.36, 0.5), (235, 225, 45)),
        "white-1": ((0.38, 0.0, 0.48, 0.5), (240, 240, 235)),
        "white-2": ((0.50, 0.0, 0.60, 0.5), (235, 235, 230)),
        "outlier": ((0.62, 0.0, 0.72, 0.5), (200, 20, 20)),
    }
    predictions = []
    for candidate_id, (box_xywh, rgb) in boxes.items():
        x, y, x2, y2 = box_xywh
        pixels[int(y * height) : int(y2 * height), int(x * width) : int(x2 * width)] = rgb
        predictions.append(_track(candidate_id, BoundingBox(x=x, y=y, width=x2 - x, height=y2 - y)))
    colored_image = Image.fromarray(pixels)

    flagged = flag_jersey_color_outliers(colored_image, predictions)
    by_id = {p.candidate_id: p for p in flagged}
    assert by_id["outlier"].jersey_color_outlier is True
    assert by_id["yellow-1"].jersey_color_outlier is False
    assert by_id["white-1"].jersey_color_outlier is False
    # Never touches role/team -- those still require a human.
    assert all(p.person_role is None and p.team is None for p in flagged)


def test_flag_jersey_color_outliers_excludes_small_distant_boxes_from_clustering():
    """Regression for a real false positive: a small, distant crowd/mascot
    box (height ratio 0.29 vs. the tallest on-court box in the same frame)
    was previously flagged as a color outlier purely because it wasn't a
    clustering candidate at all -- not because its color was genuinely
    distinct from either team. Without a real court calibration, box
    height relative to the frame's tallest detection is the only
    available "is this even at court level" signal."""
    width, height = 200, 200
    image = Image.new("RGB", (width, height), (0, 0, 0))
    pixels = np.array(image)
    boxes = {
        "yellow-1": ((0.02, 0.0, 0.12, 0.5), (230, 220, 40)),
        "yellow-2": ((0.14, 0.0, 0.24, 0.5), (225, 215, 35)),
        "yellow-3": ((0.26, 0.0, 0.36, 0.5), (235, 225, 45)),
        "white-1": ((0.38, 0.0, 0.48, 0.5), (240, 240, 235)),
        "white-2": ((0.50, 0.0, 0.60, 0.5), (235, 235, 230)),
        # A small, distant crowd figure at ~15% of the on-court boxes'
        # height, in a color that matches neither team -- must NOT be
        # flagged, since it's excluded from clustering entirely.
        "distant-crowd-member": ((0.62, 0.0, 0.68, 0.075), (60, 200, 220)),
    }
    predictions = []
    for candidate_id, (box_xywh, rgb) in boxes.items():
        x, y, x2, y2 = box_xywh
        pixels[int(y * height) : int(y2 * height), int(x * width) : int(x2 * width)] = rgb
        predictions.append(_track(candidate_id, BoundingBox(x=x, y=y, width=x2 - x, height=y2 - y)))
    colored_image = Image.fromarray(pixels)

    flagged = flag_jersey_color_outliers(colored_image, predictions)
    by_id = {p.candidate_id: p for p in flagged}
    assert by_id["distant-crowd-member"].jersey_color_outlier is False
    assert by_id["yellow-1"].jersey_color_outlier is False
    assert by_id["white-1"].jersey_color_outlier is False


def test_config_hash_is_stable_and_excludes_checkpoint_location():
    first = SmokeRunConfig(
        pipeline_run_id="pipeline-1",
        model_run_id="model-1",
        code_commit="abcdef1",
        source_sha256="d" * 64,
        checkpoint_path="C:/one/model.pth",
    )
    second = first.model_copy(update={"checkpoint_path": "D:/cache/model.pth"})
    assert config_sha256(first) == config_sha256(second)
