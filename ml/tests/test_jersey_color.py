import numpy as np
import pytest

from volley_ml.detection.jersey_color import cluster_jersey_colors, dominant_torso_color


def _solid_color_image(height: int, width: int, rgb: tuple[int, int, int]) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :] = rgb
    return image


def test_dominant_torso_color_reads_a_solid_colored_box():
    image = _solid_color_image(200, 100, (30, 120, 200))
    color = dominant_torso_color(image, (10.0, 10.0, 90.0, 190.0))
    assert color == (30, 120, 200)


def test_dominant_torso_color_ignores_a_different_colored_head_and_legs():
    """The torso band (25%-55% of box height) must dominate the result
    even when the rest of the box (head, legs, background) is a very
    different color -- proves the crop is actually restricted to the
    torso band, not averaging the whole box."""
    image = _solid_color_image(200, 100, (255, 0, 0))  # background/limbs: red
    image[50:110, :] = (0, 255, 0)  # torso band (25%-55% of a 0-200 box): green
    color = dominant_torso_color(image, (0.0, 0.0, 100.0, 200.0))
    assert color == (0, 255, 0)


def test_dominant_torso_color_rejects_a_degenerate_bbox():
    image = _solid_color_image(50, 50, (10, 10, 10))
    with pytest.raises(ValueError, match="positive width and height"):
        dominant_torso_color(image, (10.0, 10.0, 10.0, 40.0))


def test_cluster_jersey_colors_skips_clustering_with_too_few_boxes():
    colors = {"a": (255, 0, 0), "b": (0, 255, 0)}
    results = cluster_jersey_colors(colors, min_boxes_to_cluster=4)
    assert all(r.cluster_id is None and not r.is_color_outlier for r in results.values())


def test_cluster_jersey_colors_groups_two_teams_and_flags_the_outlier():
    """Two clear jersey-color groups (yellow team, white team) plus one
    clearly distinct color (a red-shirted libero/official) -- the outlier
    must be flagged, and the two majority teams must NOT be flagged."""
    colors = {
        "yellow-1": (230, 220, 40),
        "yellow-2": (225, 215, 35),
        "yellow-3": (235, 225, 45),
        "white-1": (240, 240, 235),
        "white-2": (235, 235, 230),
        "white-3": (245, 245, 240),
        "libero-red": (200, 20, 20),
    }
    results = cluster_jersey_colors(colors)
    assert not results["yellow-1"].is_color_outlier
    assert not results["white-1"].is_color_outlier
    assert results["libero-red"].is_color_outlier
    # The two majority teams must land in different clusters.
    assert results["yellow-1"].cluster_id != results["white-1"].cluster_id
    # Teammates share a cluster.
    assert (
        results["yellow-1"].cluster_id
        == results["yellow-2"].cluster_id
        == results["yellow-3"].cluster_id
    )


def test_cluster_jersey_colors_is_deterministic():
    colors = {
        "a": (10, 200, 30),
        "b": (15, 195, 35),
        "c": (200, 10, 20),
        "d": (195, 15, 25),
        "e": (12, 198, 28),
    }
    first = cluster_jersey_colors(colors)
    second = cluster_jersey_colors(colors)
    assert first == second
