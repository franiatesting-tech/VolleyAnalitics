"""Tests for volley_ml.detection.tiling -- the near/far crop-and-merge
support for tiled inference (see tiling.py's own docstring for why this
exists)."""

import pytest

from volley_ml.detection.tiling import crop_box_px, merge_tiled_person_boxes


def test_crop_box_uses_full_width_and_configured_height_fraction():
    assert crop_box_px(640, 360, height_fraction=0.6) == (0, 0, 640, 216)


def test_crop_box_defaults_to_the_module_constant_fraction():
    assert crop_box_px(1000, 1000) == (0, 0, 1000, 600)


def test_crop_box_rejects_non_positive_dimensions():
    with pytest.raises(ValueError):
        crop_box_px(0, 360)


def test_crop_box_rejects_out_of_range_fraction():
    with pytest.raises(ValueError):
        crop_box_px(640, 360, height_fraction=1.5)


def test_merge_prefers_crop_box_on_overlap():
    full_frame = [("full-0", 10.0, 10.0, 30.0, 40.0, 0.5)]
    crop = [("crop-0", 11.0, 11.0, 29.0, 39.0, 0.9)]
    merged = merge_tiled_person_boxes(full_frame, crop)
    assert merged == [("crop-0", 11.0, 11.0, 29.0, 39.0, 0.9)]


def test_merge_keeps_a_unique_full_frame_box():
    full_frame = [("full-0", 10.0, 10.0, 30.0, 40.0, 0.5)]
    crop = [("crop-0", 200.0, 200.0, 220.0, 230.0, 0.9)]
    merged = merge_tiled_person_boxes(full_frame, crop)
    assert set(merged) == {
        ("full-0", 10.0, 10.0, 30.0, 40.0, 0.5),
        ("crop-0", 200.0, 200.0, 220.0, 230.0, 0.9),
    }


def test_empty_crop_list_is_tiling_disabled_parity():
    full_frame = [("full-0", 10.0, 10.0, 30.0, 40.0, 0.5)]
    assert merge_tiled_person_boxes(full_frame, []) == full_frame


def test_merge_keeps_multiple_unique_crop_boxes():
    full_frame: list = []
    crop = [
        ("crop-0", 0.0, 0.0, 10.0, 10.0, 0.6),
        ("crop-1", 50.0, 50.0, 60.0, 60.0, 0.7),
    ]
    merged = merge_tiled_person_boxes(full_frame, crop)
    assert set(merged) == set(crop)
