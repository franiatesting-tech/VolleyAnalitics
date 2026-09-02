"""Maps the 10 named court keypoints (`volley_domain.annotation.
COURT_KEYPOINT_NAMES`) to their real-world position in meters, using the
coordinate convention `docs/datasets/PROFESSIONAL_ANNOTATION_PROTOCOL.md`
fixes for any calibration: origin at the near-left corner, x across the
court's 9m width, y toward the far baseline over 18m. This is the target
side of the point correspondences `estimate_homography` (geometry.py) fits
a homography against -- a human (or, eventually, an auto-detector) supplies
the pixel side; this module supplies the known, fixed world side.
"""

from __future__ import annotations

from volley_domain.annotation import COURT_KEYPOINT_NAMES

COURT_KEYPOINT_WORLD_POSITIONS_M: dict[str, tuple[float, float]] = {
    "near_baseline_left": (0.0, 0.0),
    "near_baseline_right": (9.0, 0.0),
    "near_attack_line_left": (0.0, 3.0),
    "near_attack_line_right": (9.0, 3.0),
    "centerline_left": (0.0, 9.0),
    "centerline_right": (9.0, 9.0),
    "far_attack_line_left": (0.0, 15.0),
    "far_attack_line_right": (9.0, 15.0),
    "far_baseline_left": (0.0, 18.0),
    "far_baseline_right": (9.0, 18.0),
}

assert set(COURT_KEYPOINT_WORLD_POSITIONS_M) == set(COURT_KEYPOINT_NAMES), (
    "COURT_KEYPOINT_WORLD_POSITIONS_M must cover exactly the same names as "
    "volley_domain.annotation.COURT_KEYPOINT_NAMES -- a mismatch here would "
    "silently drop a keypoint from every calibration fit."
)
