"""Heuristic jersey-color clustering for reviewer-assist team grouping.

Not a source of ground truth, and never wired to assert a person's actual
team or role -- it only helps a human reviewer move faster and prioritizes
the review queue. See PROFESSIONAL_ANNOTATION_PROTOCOL.md's person-role
section: "Team, jersey and roster position may be `unknown`; uncertain
identity must not be guessed from appearance."

What this actually does: groups on-court-sized bounding boxes in one frame
by their dominant torso color into up to two majority clusters (a team's
jersey color is real, strong, always-present visual signal that needs no
volleyball-specific training data to exploit), and flags any box whose
torso color sits far from both cluster centroids as a color outlier -- a
candidate libero, official, or referee wearing a visually distinct color,
exactly the kind of person the screenshot-driven review in
PROJECT_STATUS.md's continuation session called out (a libero identified
"by jersey color" is precisely this signal, made explicit and reviewable
rather than left to an annotator's unaided eye). The output is a review-
priority signal (`is_color_outlier`), never a role or team assignment --
`PlayerTrackPreannotation.team`/`person_role` still require independent
human confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class JerseyColorResult:
    candidate_id: str
    dominant_rgb: tuple[int, int, int]
    cluster_id: int | None  # None if too few boxes in the frame to cluster meaningfully
    distance_to_nearest_cluster: float | None
    is_color_outlier: bool


def dominant_torso_color(
    image: NDArray[np.uint8], bbox_xyxy_px: tuple[float, float, float, float]
) -> tuple[int, int, int]:
    """Median RGB of the box's torso band: 25%-55% down from the top of
    the box, inset 25% from each side. Avoids head/hair, hands/arms,
    shorts and background bleed at the box edges -- the torso band is
    where a jersey's own color is most reliably visible and least
    occluded by motion blur or limb movement. Median, not mean, resists a
    handful of background/skin-tone/shadow outlier pixels skewing the
    result. `image` is an HxWx3 uint8 RGB array (e.g. `np.asarray(pil_image.convert("RGB"))`)."""
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must be an HxWx3 RGB array")
    image_height, image_width = image.shape[0], image.shape[1]
    x1, y1, x2, y2 = bbox_xyxy_px
    width = x2 - x1
    height = y2 - y1
    if width <= 0 or height <= 0:
        raise ValueError("bbox must have positive width and height")

    torso_top = int(round(y1 + 0.25 * height))
    torso_bottom = int(round(y1 + 0.55 * height))
    torso_left = int(round(x1 + 0.25 * width))
    torso_right = int(round(x2 - 0.25 * width))
    torso_top = max(0, min(torso_top, image_height))
    torso_bottom = max(torso_top + 1, min(torso_bottom, image_height))
    torso_left = max(0, min(torso_left, image_width))
    torso_right = max(torso_left + 1, min(torso_right, image_width))

    crop = image[torso_top:torso_bottom, torso_left:torso_right]
    if crop.size == 0:
        raise ValueError("torso crop is empty -- bbox too small or entirely out of frame")
    median = np.median(crop.reshape(-1, 3), axis=0)
    return (int(median[0]), int(median[1]), int(median[2]))


def _hue_saturation_value_features(rgb: NDArray[np.float64]) -> NDArray[np.float64]:
    """Converts Nx3 RGB (0-255) into Nx3 features `(S*cos(2*pi*H), S*sin(2*pi*H), V)`
    -- saturation-weighted hue as a 2D point on the color wheel, plus
    value. This, not raw RGB, is what jersey-color clustering should
    measure distance in: two saturated colors of different hue (e.g. a
    yellow jersey and a red jersey) are genuinely different team colors,
    but raw RGB Euclidean distance can put a bright yellow *closer* to a
    near-white jersey than to a red one purely because yellow and white
    are both "bright" -- verified directly: (230,220,40) vs (240,240,235)
    is ~196 in raw RGB but (230,220,40) vs (200,20,20) is ~203, wrongly
    suggesting yellow resembles white more than red. Saturation-weighting
    fixes this because white/black/gray (low saturation) collapse toward
    the origin regardless of their noisy/meaningless hue, while two
    distinctly-colored jerseys stay separated by real hue difference."""
    max_channel = rgb.max(axis=1)
    min_channel = rgb.min(axis=1)
    chroma = max_channel - min_channel
    value = max_channel / 255.0
    saturation = np.divide(chroma, max_channel, out=np.zeros_like(chroma), where=max_channel > 0)

    red, green, blue = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    hue = np.zeros_like(chroma)
    safe_chroma = np.where(chroma == 0, 1.0, chroma)  # avoid divide-by-zero; hue is 0 anyway
    is_red_max = (max_channel == red) & (chroma > 0)
    is_green_max = (max_channel == green) & (chroma > 0)
    is_blue_max = (max_channel == blue) & (chroma > 0)
    hue = np.where(is_red_max, ((green - blue) / safe_chroma) % 6.0, hue)
    hue = np.where(is_green_max, ((blue - red) / safe_chroma) + 2.0, hue)
    hue = np.where(is_blue_max, ((red - green) / safe_chroma) + 4.0, hue)
    hue_radians = hue * (np.pi / 3.0)  # hue is in [0, 6); scale to [0, 2*pi)

    return np.stack(
        [saturation * np.cos(hue_radians), saturation * np.sin(hue_radians), value], axis=1
    )


def _two_means(colors: NDArray[np.float64], *, iterations: int = 20) -> NDArray[np.float64]:
    """Deterministic k=2 Lloyd's-algorithm clustering, seeded from (1) the
    medoid -- the color with the smallest total distance to every other
    color, which in a frame dominated by two real teams plus a handful of
    outliers reliably lands inside whichever team happens to be larger or
    more central -- and (2) the color farthest from that medoid, standing
    in for "the other group." This must be reproducible run-to-run for the
    exact same input, since it feeds a review-priority score a QA report
    will compare across runs.

    Deliberately NOT seeded from the two mutually most-distant colors: with
    exactly the scenario this module exists for (two real teams plus 1-2
    genuinely distinct outlier jerseys), the single most extreme pairwise
    distance is often the outlier itself paired with the color furthest
    from it -- letting a lone outlier hijack a seed and split the two real
    teams incorrectly. The medoid is comparatively robust to a small
    number of outliers by construction (verified by
    test_cluster_jersey_colors_groups_two_teams_and_flags_the_outlier)."""
    pairwise = np.linalg.norm(colors[:, None, :] - colors[None, :, :], axis=2)
    medoid_index = int(np.argmin(pairwise.sum(axis=1)))
    farthest_index = int(np.argmax(pairwise[medoid_index]))
    centroids = np.stack([colors[medoid_index], colors[farthest_index]])
    for _ in range(iterations):
        distances = np.linalg.norm(colors[:, None, :] - centroids[None, :, :], axis=2)
        assignments = np.argmin(distances, axis=1)
        new_centroids = centroids.copy()
        for cluster_id in (0, 1):
            members = colors[assignments == cluster_id]
            if len(members) > 0:
                new_centroids[cluster_id] = members.mean(axis=0)
        if np.allclose(new_centroids, centroids):
            centroids = new_centroids
            break
        centroids = new_centroids
    return centroids


def cluster_jersey_colors(
    colors: dict[str, tuple[int, int, int]],
    *,
    neighbor_radius: float = 0.35,
    min_neighbors: int = 1,
    min_boxes_to_cluster: int = 4,
) -> dict[str, JerseyColorResult]:
    """Flags a torso color as an outlier when it has *no close company* in
    the frame, rather than by distance to a k=2 cluster centroid.

    A cluster-centroid-distance definition has a real blind spot this
    module specifically needs to avoid: a genuinely distinct color (a lone
    libero/official) can end up seeded as its *own* one-member cluster,
    whose "distance to its own centroid" is trivially 0 -- rewarding
    exactly the case this function exists to catch. Neighbor density does
    not have this failure mode: a real team member has several teammates
    within a small color radius; a lone distinctly-colored person does
    not, regardless of how the rest of the frame happens to split into
    clusters.

    Below `min_boxes_to_cluster` candidates there is too little context to
    call anything an outlier -- every result gets `cluster_id=None`,
    `is_color_outlier=False` rather than a false-confidence guess from a
    near-empty frame.

    Distance (both for neighbor-counting and the informational
    `cluster_id`/`distance_to_nearest_cluster`) is computed in saturation-
    weighted-hue-plus-value feature space (see
    `_hue_saturation_value_features`), not raw RGB -- raw RGB Euclidean
    distance can rank a bright yellow as closer to near-white than to red
    purely from shared brightness, which is exactly backwards for telling
    jersey colors apart. In that feature space each axis is bounded
    (saturation-weighted hue components in [-1, 1], value in [0, 1]), so
    the maximum possible distance is 3; `neighbor_radius=0.35` is
    deliberately tight (same team, allowing for lighting/motion-blur
    variation, not "vaguely similar"). `cluster_id` still comes from k=2
    clustering across every point (informational grouping hint for the
    reviewer only -- it does not gate `is_color_outlier`).

    Both thresholds are unvalidated against real footage (no calibrated
    ground truth exists yet, see TECH_DEBT.md) -- re-tune once real
    reviewer feedback exists on how often this over/under-flags.
    """
    candidate_ids = list(colors.keys())
    if len(candidate_ids) < min_boxes_to_cluster:
        return {
            candidate_id: JerseyColorResult(
                candidate_id=candidate_id,
                dominant_rgb=colors[candidate_id],
                cluster_id=None,
                distance_to_nearest_cluster=None,
                is_color_outlier=False,
            )
            for candidate_id in candidate_ids
        }

    rgb_array = np.asarray([colors[cid] for cid in candidate_ids], dtype=np.float64)
    feature_array = _hue_saturation_value_features(rgb_array)

    pairwise = np.linalg.norm(feature_array[:, None, :] - feature_array[None, :, :], axis=2)
    np.fill_diagonal(pairwise, np.inf)
    neighbor_counts = (pairwise <= neighbor_radius).sum(axis=1)
    is_outlier_mask = neighbor_counts < min_neighbors

    # Fit the informational cluster_id/distance only on non-outlier points
    # -- a lone distinctly-colored outlier would otherwise distort the
    # two-means fit for the two real teams (verified directly: including
    # it merged both real teams into one cluster in an earlier version of
    # this function). Outliers still get assigned to their nearest
    # centroid afterward, just not allowed to influence where the
    # centroids land.
    fit_source = feature_array[~is_outlier_mask] if is_outlier_mask.any() else feature_array
    centroids = _two_means(fit_source) if len(fit_source) >= 2 else feature_array[:2]
    distances_to_centroids = np.linalg.norm(
        feature_array[:, None, :] - centroids[None, :, :], axis=2
    )
    nearest_cluster = np.argmin(distances_to_centroids, axis=1)
    nearest_distance = np.min(distances_to_centroids, axis=1)

    results: dict[str, JerseyColorResult] = {}
    for index, candidate_id in enumerate(candidate_ids):
        results[candidate_id] = JerseyColorResult(
            candidate_id=candidate_id,
            dominant_rgb=colors[candidate_id],
            cluster_id=int(nearest_cluster[index]),
            distance_to_nearest_cluster=float(nearest_distance[index]),
            is_color_outlier=bool(is_outlier_mask[index]),
        )
    return results
