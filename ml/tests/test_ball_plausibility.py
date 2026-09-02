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
    is_ball_at_person_foot_level,
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


def test_abstains_on_a_tiny_crop_even_with_no_ball_color_pattern():
    # 9x9 pre-inset -> 7x7 = 49px^2 post-inset, below _MIN_CROP_AREA_PX
    # (64) -- real ball detections at 640x360 broadcast scale are
    # genuinely this small (verified against real match footage), too
    # small/blur-degraded for the color fractions below to be a reliable
    # signal. A uniformly dark patch (the "definitely not a ball" case at
    # normal scale) must still pass at this scale -- abstain, not reject.
    image = _solid_patch(9, 9, (20, 20, 20))
    assert has_ball_color_pattern(image, (0, 0, 9, 9)) is True


def test_applies_the_normal_thresholds_right_at_the_crop_area_floor():
    # 10x10 pre-inset -> 8x8 = 64px^2 post-inset, exactly at the floor --
    # not below it, so the normal color-fraction thresholds still apply
    # and a genuinely colorless patch is still rejected.
    image = _solid_patch(10, 10, (20, 20, 20))
    assert has_ball_color_pattern(image, (0, 0, 10, 10)) is False


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


def test_shoe_fully_inside_a_persons_foot_zone_is_vetoed():
    # A person box 100px tall, 40px wide, feet at y=100 -- a small "ball"
    # box entirely within the bottom 28% (the foot zone) is almost
    # certainly the person's own shoe.
    person = (0.0, 0.0, 40.0, 100.0)
    shoe_like_ball = (5.0, 85.0, 20.0, 98.0)
    assert is_ball_at_person_foot_level(shoe_like_ball, [person]) is True


def test_ball_near_a_raised_hand_is_not_vetoed():
    # Same person box, but the "ball" is up near the head/raised-hand
    # region (upper 70%) -- a real serve/spike/block contact, must not be
    # rejected.
    person = (0.0, 0.0, 40.0, 100.0)
    ball_at_raised_hand = (10.0, 5.0, 25.0, 15.0)
    assert is_ball_at_person_foot_level(ball_at_raised_hand, [person]) is False


def test_ball_only_slightly_overlapping_a_foot_is_not_vetoed():
    # A real dig: the ball sits beside, not swallowed by, the digger's own
    # foot zone -- containment is well below the veto's threshold.
    person = (0.0, 0.0, 40.0, 100.0)
    ball_beside_foot = (30.0, 85.0, 60.0, 98.0)  # only its left sliver overlaps
    assert is_ball_at_person_foot_level(ball_beside_foot, [person]) is False


def test_ball_with_no_overlap_with_any_person_is_unaffected():
    person = (0.0, 0.0, 40.0, 100.0)
    ball_far_away = (200.0, 200.0, 215.0, 215.0)
    assert is_ball_at_person_foot_level(ball_far_away, [person]) is False


def test_ball_vetoed_by_either_of_two_overlapping_persons():
    person_a = (0.0, 0.0, 40.0, 100.0)
    person_b = (10.0, 0.0, 50.0, 100.0)
    shoe_like_ball = (15.0, 85.0, 30.0, 98.0)
    assert is_ball_at_person_foot_level(shoe_like_ball, [person_a, person_b]) is True
