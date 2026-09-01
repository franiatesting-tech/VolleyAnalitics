"""Tests for volley_ml.detection.ball_plausibility -- the per-frame
color/shape gate that rejects ball-class detections that are almost
certainly a shoe, a crowd-area object, or another non-ball, before they
ever reach services/worker (see ball_plausibility.py's own docstring for
the manufacturer-color rationale)."""

import numpy as np
import pytest

from volley_ml.detection.ball_plausibility import (
    has_ball_color_pattern,
    has_plausible_ball_shape,
)


def _solid_patch(width: int, height: int, color: tuple[int, int, int]) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :] = color
    return image


def _two_tone_patch(
    width: int, height: int, left_color: tuple[int, int, int], right_color: tuple[int, int, int]
) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    mid = width // 2
    image[:, :mid] = left_color
    image[:, mid:] = right_color
    return image


def test_white_and_green_pattern_is_plausible_molten_colors():
    # Molten V5M4500: white + green + red panels.
    image = _two_tone_patch(40, 40, (250, 250, 250), (0, 160, 60))
    assert has_ball_color_pattern(image, (0, 0, 40, 40)) is True


def test_white_and_blue_pattern_is_plausible_mikasa_colors():
    # Mikasa V200W: white + blue + yellow panels.
    image = _two_tone_patch(40, 40, (245, 245, 245), (30, 90, 200))
    assert has_ball_color_pattern(image, (0, 0, 40, 40)) is True


def test_uniform_dark_patch_has_no_ball_color_pattern():
    # A shoe or a shadowed crowd object -- no white, no saturated accent.
    image = _solid_patch(40, 40, (20, 20, 20))
    assert has_ball_color_pattern(image, (0, 0, 40, 40)) is False


def test_uniform_white_patch_alone_is_not_enough():
    # White area alone (e.g. a line, a wall) without any accent color
    # isn't a ball pattern either -- the ball's own signal is the
    # combination of both.
    image = _solid_patch(40, 40, (250, 250, 250))
    assert has_ball_color_pattern(image, (0, 0, 40, 40)) is False


def test_skin_tone_patch_has_no_ball_color_pattern():
    # A hand/arm crop -- warm, low-saturation, not white and not one of
    # the accent hue bands.
    image = _solid_patch(40, 40, (200, 160, 130))
    assert has_ball_color_pattern(image, (0, 0, 40, 40)) is False


def test_rejects_a_degenerate_bbox():
    image = _solid_patch(10, 10, (255, 255, 255))
    with pytest.raises(ValueError):
        has_ball_color_pattern(image, (5, 5, 5, 10))


def test_square_bbox_is_a_plausible_ball_shape():
    assert has_plausible_ball_shape((10.0, 10.0, 30.0, 30.0)) is True


def test_elongated_bbox_is_not_a_plausible_ball_shape():
    # A shoe or a courtside sign -- much wider than tall.
    assert has_plausible_ball_shape((10.0, 50.0, 70.0, 60.0)) is False


def test_moderately_blurred_bbox_still_passes():
    # Motion blur along the direction of travel genuinely elongates a fast
    # ball's box -- this should stay within tolerance.
    assert has_plausible_ball_shape((10.0, 10.0, 28.0, 20.0)) is True
