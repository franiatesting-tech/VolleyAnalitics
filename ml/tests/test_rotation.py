import pytest
from volley_domain.court import ZONE_ANCHORS

from volley_ml.court.rotation import (
    FULL_COURT_LENGTH_M,
    FULL_COURT_WIDTH_M,
    HALF_COURT_LENGTH_M,
    is_legal_front_row_attacker,
    team_attacking_frame_from_court_plane,
    team_zone_from_court_plane,
)


def test_near_half_baseline_maps_to_normalized_y_one():
    _, y = team_attacking_frame_from_court_plane(4.5, 0.0, team_half="near")
    assert y == pytest.approx(1.0)


def test_near_half_net_maps_to_normalized_y_zero():
    _, y = team_attacking_frame_from_court_plane(4.5, HALF_COURT_LENGTH_M, team_half="near")
    assert y == pytest.approx(0.0)


def test_far_half_baseline_maps_to_normalized_y_one():
    _, y = team_attacking_frame_from_court_plane(4.5, FULL_COURT_LENGTH_M, team_half="far")
    assert y == pytest.approx(1.0)


def test_far_half_net_maps_to_normalized_y_zero():
    _, y = team_attacking_frame_from_court_plane(4.5, HALF_COURT_LENGTH_M, team_half="far")
    assert y == pytest.approx(0.0)


def test_rejects_a_point_outside_the_court_plane():
    with pytest.raises(ValueError, match="court width"):
        team_attacking_frame_from_court_plane(-0.5, 5.0, team_half="near")
    with pytest.raises(ValueError, match="court length"):
        team_attacking_frame_from_court_plane(4.5, 30.0, team_half="near")


def test_mirror_x_flips_the_normalized_x_axis():
    x_unmirrored, _ = team_attacking_frame_from_court_plane(2.0, 4.0, team_half="near")
    x_mirrored, _ = team_attacking_frame_from_court_plane(2.0, 4.0, team_half="near", mirror_x=True)
    assert x_mirrored == pytest.approx(1.0 - x_unmirrored)


@pytest.mark.parametrize("zone", [1, 2, 3, 4, 5, 6])
def test_zone_anchor_round_trips_through_the_full_pipeline_on_the_near_half(zone):
    """A player standing exactly at a zone's own anchor point, converted to
    real court-plane meters and back through the full pipeline, must
    resolve to that same zone -- the core correctness invariant this
    module exists to guarantee."""
    anchor_x, anchor_y = ZONE_ANCHORS[zone]
    x_meters = anchor_x * FULL_COURT_WIDTH_M
    y_meters = (1.0 - anchor_y) * HALF_COURT_LENGTH_M  # near half: baseline (y=1) is y_meters=0
    resolved_zone, row = team_zone_from_court_plane(x_meters, y_meters, team_half="near")
    assert resolved_zone == zone
    expected_row = "front" if anchor_y < 0.5 else "back"
    assert row == expected_row


@pytest.mark.parametrize("zone", [1, 2, 3, 4, 5, 6])
def test_zone_anchor_round_trips_through_the_full_pipeline_on_the_far_half(zone):
    anchor_x, anchor_y = ZONE_ANCHORS[zone]
    x_meters = anchor_x * FULL_COURT_WIDTH_M
    y_meters = HALF_COURT_LENGTH_M + anchor_y * HALF_COURT_LENGTH_M  # far half: baseline is y=18
    resolved_zone, row = team_zone_from_court_plane(x_meters, y_meters, team_half="far")
    assert resolved_zone == zone


def test_front_row_zones_are_exactly_two_three_four():
    assert is_legal_front_row_attacker(2)
    assert is_legal_front_row_attacker(3)
    assert is_legal_front_row_attacker(4)
    assert not is_legal_front_row_attacker(1)
    assert not is_legal_front_row_attacker(5)
    assert not is_legal_front_row_attacker(6)
