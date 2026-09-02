"""Near/far tiled inference support -- a documented answer to real user
feedback that far-side (upper-frame, near-net) players are poorly detected
on a standard elevated wide-angle broadcast shot. A single full-frame
RF-DETR nano pass gives the far team too few effective pixels; running a
second forward pass on a cropped upper region of the frame gives that
region proportionally more effective resolution, without any retraining.

`FAR_CROP_HEIGHT_FRACTION` is a documented broadcast-framing assumption
(the far team sits in the upper ~60% of a standard elevated wide shot),
same class of hardcoded-but-documented assumption as
ball_plausibility.py's manufacturer accent colors -- not fitted to any
real data, and worth re-checking against real footage from an unusual
camera angle.
"""

from __future__ import annotations

FAR_CROP_HEIGHT_FRACTION = 0.6
FAR_MERGE_IOU_THRESHOLD = 0.4

# (candidate_id, x1, y1, x2, y2, confidence) -- matches server.py's own
# internal person_boxes tuple shape, so no reshaping is needed at the call
# site.
PersonBox = tuple[str, float, float, float, float, float]


def crop_box_px(
    image_width: int, image_height: int, *, height_fraction: float = FAR_CROP_HEIGHT_FRACTION
) -> tuple[int, int, int, int]:
    """The crop always starts at the image's own (0, 0) -- so a box the
    model returns against this crop is already in full-frame pixel
    coordinates, with no remapping needed before merging."""
    if image_width <= 0 or image_height <= 0:
        raise ValueError("image_width and image_height must be positive")
    if not 0.0 < height_fraction <= 1.0:
        raise ValueError("height_fraction must be in (0, 1]")
    return (0, 0, image_width, int(round(image_height * height_fraction)))


def _iou(a: PersonBox, b: PersonBox) -> float:
    _, ax1, ay1, ax2, ay2, _ = a
    _, bx1, by1, bx2, by2, _ = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if intersection <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def merge_tiled_person_boxes(
    full_frame_boxes: list[PersonBox],
    crop_boxes: list[PersonBox],
    *,
    iou_threshold: float = FAR_MERGE_IOU_THRESHOLD,
) -> list[PersonBox]:
    """Greedy IoU match: every crop-pass box is kept (it has higher
    effective resolution in the overlap band, so its localization wins),
    its matching full-frame box (if any, IoU >= iou_threshold) is dropped,
    and every unmatched full-frame box is kept as-is. Deduplication matters
    beyond cosmetics: the frontend's on-court occupancy classifier caps
    players at 6/side by confidence rank -- an undeduplicated double-box
    for one real player wastes a ranked slot a genuinely different,
    undetected player should have gotten."""
    matched_full_frame_indices: set[int] = set()
    for crop_box in crop_boxes:
        best_index, best_iou = None, 0.0
        for index, full_frame_box in enumerate(full_frame_boxes):
            if index in matched_full_frame_indices:
                continue
            score = _iou(crop_box, full_frame_box)
            if score > best_iou:
                best_index, best_iou = index, score
        if best_index is not None and best_iou >= iou_threshold:
            matched_full_frame_indices.add(best_index)

    kept_full_frame = [
        box for index, box in enumerate(full_frame_boxes) if index not in matched_full_frame_indices
    ]
    return kept_full_frame + list(crop_boxes)
