"""Rejects ball-class detections that are almost certainly not a real
volleyball, using only the candidate patch's own color and shape -- a
cheap, single-frame filter that runs before any temporal reasoning
(contrast with services/worker/.../ball_filtering.py's
find_static_false_positive_ids, which needs cross-frame timestamps and
lives downstream in the worker once frames are already persisted).

Why this exists: RF-DETR nano's generic COCO "sports ball" class was never
fine-tuned for volleyball (see server.py's own docstring on
_COCO_SPORTS_BALL_CLASS_ID) and, run at a low confidence threshold to keep
recall usable for a small fast-moving object, regularly fires on shoes,
crowd-area objects (advertising boards, railings, seat backs) and other
round-ish or bright objects that are not the ball -- exactly what the
product owner reported after reviewing real footage.

A real volleyball's own strongest, training-data-free signal is its
manufacturer color scheme, verified directly against the product owner's
own reference photos: Mikasa V200W is white + blue + yellow; Molten
V5M4500/V4200 is white + green + red. Every FIVB-approved ball is
white-dominant with one or two saturated accent colors arranged in a
curved panel pattern, and every ball is round (bbox aspect ratio near 1),
unlike a shoe or most crowd objects.

This is a heuristic gate, not ground truth -- deliberately conservative
(reject only when the patch has neither a plausible accent-color pattern
nor a plausible round shape), since a missed real ball (false negative)
silently thins an already sparse trajectory, which is worse for this
pipeline's goal -- reconstructing rally trajectories -- than an occasional
shoe slipping through. Thresholds below are unvalidated against real
footage (no calibrated ground truth exists yet, same caveat as
jersey_color.py's own clustering thresholds) -- re-tune once real reviewer
feedback exists on how often this over/under-rejects.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# Hue ranges in degrees (0-360), generous bands rather than narrow color
# matching -- JPEG compression, motion blur and a small patch size all
# blur real hue, and this only needs to catch *some* accent color, not
# classify which ball model it is.
_ACCENT_HUE_RANGES_DEG: dict[str, list[tuple[float, float]]] = {
    "red": [(0.0, 15.0), (345.0, 360.0)],
    "yellow": [(35.0, 65.0)],
    "green": [(70.0, 160.0)],
    "blue": [(180.0, 250.0)],
}
_WHITE_MIN_VALUE = 0.55
_WHITE_MAX_SATURATION = 0.35
_ACCENT_MIN_SATURATION = 0.35
_MIN_WHITE_FRACTION = 0.12
_MIN_ACCENT_FRACTION = 0.08
# A ball's box should be close to square; a fast ball's motion blur
# genuinely elongates it along its direction of travel, so this stays
# generous rather than requiring a near-perfect square.
_MAX_ASPECT_RATIO = 1.9
# Below this many post-inset pixels, has_ball_color_pattern abstains
# (accepts) rather than rejects on color grounds -- verified directly
# against real 640x360 match footage that a real ball detection's box is
# often only ~10x10px pre-inset (~8x9px, ~70px^2, post-inset), close to or
# below a single H.264/JPEG macroblock. At that scale nearly every sampled
# pixel is already a compression-blurred blend of ball-white, accent
# color, motion blur and background bleed, and a 1-2px localization error
# from a low-confidence detector can shift the whole sample off the panel
# pattern -- the white/accent fractions below stop being a reliable signal
# long before they become actively misleading. The shape gate
# (has_plausible_ball_shape) still applies regardless of size.
_MIN_CROP_AREA_PX = 64

# A shoe is always physically attached to a person, specifically at foot
# level -- a real ball during a genuine contact (serve, spike, set, block)
# sits near a raised hand/arm/head instead. But a real defensive dig/floor
# save also brings the ball to foot/shin height, right beside (not inside)
# the digging player's own foot -- so this deliberately requires
# near-total containment, not mere overlap, to avoid vetoing a real dig.
# Direct response to real user feedback ("the ball is sometimes confused
# with shoes") -- unvalidated against real footage like every other
# threshold in this module; watch ModelRun.metrics'
# ball_candidates_vetoed_by_foot_overlap on the next real run and re-tune
# if it's suppressing genuine digs.
_FOOT_ZONE_HEIGHT_FRACTION = 0.28
_FOOT_OVERLAP_MIN_CONTAINMENT = 0.65


def _rgb_to_hsv(rgb: NDArray[np.float64]) -> NDArray[np.float64]:
    """Nx3 RGB (0-255) -> Nx3 (hue degrees [0,360), saturation [0,1], value [0,1])."""
    rgb01 = rgb / 255.0
    max_channel = rgb01.max(axis=1)
    min_channel = rgb01.min(axis=1)
    chroma = max_channel - min_channel
    value = max_channel
    saturation = np.divide(chroma, max_channel, out=np.zeros_like(chroma), where=max_channel > 0)

    red, green, blue = rgb01[:, 0], rgb01[:, 1], rgb01[:, 2]
    safe_chroma = np.where(chroma == 0, 1.0, chroma)
    hue = np.zeros_like(chroma)
    is_red_max = (max_channel == red) & (chroma > 0)
    is_green_max = (max_channel == green) & (chroma > 0)
    is_blue_max = (max_channel == blue) & (chroma > 0)
    hue = np.where(is_red_max, ((green - blue) / safe_chroma) % 6.0, hue)
    hue = np.where(is_green_max, ((blue - red) / safe_chroma) + 2.0, hue)
    hue = np.where(is_blue_max, ((red - green) / safe_chroma) + 4.0, hue)
    hue_deg = hue * 60.0
    return np.stack([hue_deg, saturation, value], axis=1)


def _in_hue_ranges(
    hue_deg: NDArray[np.float64], ranges: list[tuple[float, float]]
) -> NDArray[np.bool_]:
    mask = np.zeros(hue_deg.shape, dtype=bool)
    for low, high in ranges:
        mask |= (hue_deg >= low) & (hue_deg <= high)
    return mask


def has_ball_color_pattern(
    image: NDArray[np.uint8], bbox_xyxy_px: tuple[float, float, float, float]
) -> bool:
    """True if the patch has enough white area *and* enough of at least
    one manufacturer accent color (see module docstring) to plausibly be
    a real volleyball's panel pattern. Insets 10% from each edge first, so
    a tight-but-imperfect detector box doesn't dilute the sample with
    background pixels bleeding in at the edges (same rationale as
    dominant_torso_color's own inset in jersey_color.py). `image` is an
    HxWx3 uint8 RGB array."""
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must be an HxWx3 RGB array")
    image_height, image_width = image.shape[0], image.shape[1]
    x1, y1, x2, y2 = bbox_xyxy_px
    width = x2 - x1
    height = y2 - y1
    if width <= 0 or height <= 0:
        raise ValueError("bbox must have positive width and height")

    inset_x = width * 0.1
    inset_y = height * 0.1
    left = max(0, min(int(round(x1 + inset_x)), image_width))
    right = max(left + 1, min(int(round(x2 - inset_x)), image_width))
    top = max(0, min(int(round(y1 + inset_y)), image_height))
    bottom = max(top + 1, min(int(round(y2 - inset_y)), image_height))

    crop = image[top:bottom, left:right]
    if crop.size == 0:
        return False
    crop_area_px = crop.shape[0] * crop.shape[1]
    if crop_area_px < _MIN_CROP_AREA_PX:
        return True

    pixels = crop.reshape(-1, 3).astype(np.float64)
    hsv = _rgb_to_hsv(pixels)
    hue, saturation, value = hsv[:, 0], hsv[:, 1], hsv[:, 2]

    white_mask = (value >= _WHITE_MIN_VALUE) & (saturation <= _WHITE_MAX_SATURATION)
    white_fraction = float(white_mask.mean())

    accent_mask = np.zeros(len(pixels), dtype=bool)
    for ranges in _ACCENT_HUE_RANGES_DEG.values():
        accent_mask |= _in_hue_ranges(hue, ranges) & (saturation >= _ACCENT_MIN_SATURATION)
    accent_fraction = float(accent_mask.mean())

    return white_fraction >= _MIN_WHITE_FRACTION and accent_fraction >= _MIN_ACCENT_FRACTION


def has_plausible_ball_shape(bbox_xyxy_px: tuple[float, float, float, float]) -> bool:
    """True if the box is close enough to square to plausibly be a round
    ball rather than an elongated object (a shoe, a railing, a courtside
    sign)."""
    x1, y1, x2, y2 = bbox_xyxy_px
    width = x2 - x1
    height = y2 - y1
    if width <= 0 or height <= 0:
        return False
    ratio = max(width, height) / min(width, height)
    return ratio <= _MAX_ASPECT_RATIO


def _box_area(bbox_xyxy_px: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = bbox_xyxy_px
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _intersection_area(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    return max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)


def is_ball_at_person_foot_level(
    ball_bbox_xyxy_px: tuple[float, float, float, float],
    person_boxes_xyxy_px: list[tuple[float, float, float, float]],
    *,
    foot_zone_height_fraction: float = _FOOT_ZONE_HEIGHT_FRACTION,
    min_containment_fraction: float = _FOOT_OVERLAP_MIN_CONTAINMENT,
) -> bool:
    """True if `ball_bbox_xyxy_px` is almost certainly a shoe, not a real
    ball -- i.e. it sits nearly entirely inside the bottom
    `foot_zone_height_fraction` of some person's own box. Deliberately a
    containment check, not a mere-overlap check: a real ball beside a
    player's foot during a genuine dig should NOT be vetoed, only a
    candidate effectively swallowed by the person's own foot-level
    silhouette, which is what a shoe box necessarily is. See module
    docstring for the accepted false-negative risk this trades off."""
    ball_area = _box_area(ball_bbox_xyxy_px)
    if ball_area <= 0:
        return False
    for person_box in person_boxes_xyxy_px:
        px1, py1, px2, py2 = person_box
        person_height = py2 - py1
        if person_height <= 0:
            continue
        foot_zone = (px1, py2 - person_height * foot_zone_height_fraction, px2, py2)
        contained_fraction = _intersection_area(ball_bbox_xyxy_px, foot_zone) / ball_area
        if contained_fraction >= min_containment_fraction:
            return True
    return False
