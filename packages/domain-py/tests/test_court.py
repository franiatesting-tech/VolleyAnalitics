import pytest
from volley_domain.court import (
    ZONE_ANCHORS,
    is_front_row,
    is_in_bounds,
    mirror_for_away,
    nearest_zone,
    zone_anchor,
)


def test_mirror_is_its_own_inverse():
    for x, y in [(0.0, 0.0), (1.0, 1.0), (0.3, 0.7), (0.83, 0.92)]:
        mirrored = mirror_for_away(x, y)
        double_mirrored = mirror_for_away(*mirrored)
        assert double_mirrored == pytest.approx((x, y))


def test_mirror_of_center_is_center():
    assert mirror_for_away(0.5, 0.5) == pytest.approx((0.5, 0.5))


def test_mirror_reflects_across_both_axes():
    assert mirror_for_away(0.0, 0.0) == pytest.approx((1.0, 1.0))
    assert mirror_for_away(1.0, 0.0) == pytest.approx((0.0, 1.0))
    assert mirror_for_away(0.0, 1.0) == pytest.approx((1.0, 0.0))


def test_all_zone_anchors_are_in_bounds():
    for zone, (x, y) in ZONE_ANCHORS.items():
        assert is_in_bounds(x, y), f"zone {zone} anchor ({x}, {y}) out of bounds"


def test_all_zone_anchors_mirror_to_in_bounds_coordinates():
    for zone, (x, y) in ZONE_ANCHORS.items():
        mx, my = mirror_for_away(x, y)
        assert is_in_bounds(mx, my), f"zone {zone} mirrored anchor ({mx}, {my}) out of bounds"


def test_zone_anchor_home_matches_raw_anchor():
    for zone in ZONE_ANCHORS:
        assert zone_anchor(zone, "home") == ZONE_ANCHORS[zone]


def test_zone_anchor_away_is_mirrored():
    for zone in ZONE_ANCHORS:
        expected = mirror_for_away(*ZONE_ANCHORS[zone])
        assert zone_anchor(zone, "away") == expected


def test_zone_anchor_home_and_away_are_symmetric_around_center():
    """A zone's home and away anchors should be point-symmetric around the
    court center (0.5, 0.5) -- this is the geometric property that makes
    overlaying both teams' data in one frame meaningful."""
    for zone in ZONE_ANCHORS:
        home_x, home_y = zone_anchor(zone, "home")
        away_x, away_y = zone_anchor(zone, "away")
        assert (home_x + away_x) / 2 == pytest.approx(0.5)
        assert (home_y + away_y) / 2 == pytest.approx(0.5)


def test_is_in_bounds():
    assert is_in_bounds(0.0, 0.0)
    assert is_in_bounds(1.0, 1.0)
    assert is_in_bounds(0.5, 0.5)
    assert not is_in_bounds(-0.01, 0.5)
    assert not is_in_bounds(0.5, 1.01)


def test_nearest_zone_returns_exact_zone_at_its_own_anchor():
    for zone in ZONE_ANCHORS:
        x, y = zone_anchor(zone, "home")
        assert nearest_zone(x, y, "home") == zone


def test_nearest_zone_respects_team_frame():
    # Zone 1's home anchor should resolve to zone 1 in the away frame too,
    # once mirrored -- nearest_zone must use the correct frame internally.
    for zone in ZONE_ANCHORS:
        x, y = zone_anchor(zone, "away")
        assert nearest_zone(x, y, "away") == zone


def test_front_row_zones():
    assert is_front_row(2)
    assert is_front_row(3)
    assert is_front_row(4)
    assert not is_front_row(1)
    assert not is_front_row(5)
    assert not is_front_row(6)
