from volley_domain.annotation import COURT_KEYPOINT_NAMES

from volley_ml.court.keypoints import COURT_KEYPOINT_WORLD_POSITIONS_M


def test_covers_exactly_the_named_keypoints():
    assert set(COURT_KEYPOINT_WORLD_POSITIONS_M) == set(COURT_KEYPOINT_NAMES)


def test_no_two_keypoints_share_a_world_position():
    positions = list(COURT_KEYPOINT_WORLD_POSITIONS_M.values())
    assert len(positions) == len(set(positions))


def test_positions_are_within_the_9_by_18_meter_court():
    for x, y in COURT_KEYPOINT_WORLD_POSITIONS_M.values():
        assert 0.0 <= x <= 9.0
        assert 0.0 <= y <= 18.0


def test_left_right_pairs_share_the_same_y_and_differ_only_in_x():
    for base in (
        "near_baseline",
        "near_attack_line",
        "centerline",
        "far_attack_line",
        "far_baseline",
    ):
        left_x, left_y = COURT_KEYPOINT_WORLD_POSITIONS_M[f"{base}_left"]
        right_x, right_y = COURT_KEYPOINT_WORLD_POSITIONS_M[f"{base}_right"]
        assert left_y == right_y
        assert right_x - left_x == 9.0
