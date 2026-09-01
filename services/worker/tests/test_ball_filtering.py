from volley_worker.ball_filtering import find_static_false_positive_ids


def _det(candidate_id: str, x: float, y: float, w: float = 0.013, h: float = 0.02) -> dict:
    return {"candidate_id": candidate_id, "bbox": {"x": x, "y": y, "width": w, "height": h}}


def test_flags_a_position_recurring_across_a_long_span():
    # Reproduces the real false positive found against Nh2l4GY8JYI.mp4:
    # a "ball" at ~(0.39, 0.55) recurring every second for 13 seconds
    # straight (frames 85-97 at 1fps) -- no real in-play ball sits still
    # that long.
    detections = [(float(t), _det(f"b{t}", 0.390 + 0.0005 * t, 0.550)) for t in range(85, 98)]
    flagged = find_static_false_positive_ids(detections)
    assert flagged == {f"b{t}" for t in range(85, 98)}


def test_does_not_flag_a_genuinely_moving_trajectory():
    # A ball crossing the court over 10 seconds -- each sample is well
    # outside the cluster radius of any other sample, so nothing recurs
    # at "the same spot."
    detections = [(float(t), _det(f"b{t}", 0.1 + 0.08 * t, 0.5)) for t in range(10)]
    assert find_static_false_positive_ids(detections) == set()


def test_does_not_flag_a_brief_legitimate_pause():
    # A ball held at serve for 2 seconds, then play resumes -- shorter
    # than the 5s static-span threshold, so it must not be flagged as a
    # fixed scene object.
    detections = [
        (0.0, _det("hold-0", 0.5, 0.5)),
        (1.0, _det("hold-1", 0.5, 0.5)),
        (2.0, _det("hold-2", 0.5, 0.5)),
        (3.0, _det("serve-0", 0.55, 0.4)),
        (4.0, _det("serve-1", 0.62, 0.3)),
    ]
    assert find_static_false_positive_ids(detections) == set()


def test_flags_only_the_static_cluster_not_unrelated_moving_detections():
    # Points in the middle of the static run (e.g. static-3/static-4) may
    # genuinely have no *other* same-spot detection >=5s away within this
    # short 8-second window -- that's correct, not a bug: only pairs that
    # actually span >=5s at the same spot get flagged. The two endpoints
    # (0 and 7, a 7s span) must be flagged; no moving detection ever should.
    detections = [(float(t), _det(f"static-{t}", 0.39, 0.55)) for t in range(0, 8)] + [
        (float(t), _det(f"moving-{t}", 0.05 * t, 0.2)) for t in range(0, 8)
    ]
    flagged = find_static_false_positive_ids(detections)
    assert {"static-0", "static-7"} <= flagged
    assert flagged <= {f"static-{t}" for t in range(0, 8)}
    assert not any(candidate_id.startswith("moving-") for candidate_id in flagged)


def test_two_detections_just_outside_the_radius_are_not_clustered():
    detections = [
        (0.0, _det("a", 0.30, 0.50)),
        (10.0, _det("b", 0.40, 0.50)),  # 0.10 away -- well outside the 0.03 radius
    ]
    assert find_static_false_positive_ids(detections) == set()


def test_empty_input_returns_empty_set():
    assert find_static_false_positive_ids([]) == set()
