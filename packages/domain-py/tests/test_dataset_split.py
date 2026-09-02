import pytest
from volley_domain.dataset_split import (
    SplitUnit,
    detect_cross_split_group_leakage,
    leakage_safe_split,
)


def _units(n: int, group_prefix: str = "match") -> list[SplitUnit]:
    return [SplitUnit(video_id=f"video-{i}", group_key=f"{group_prefix}-{i}") for i in range(n)]


def test_empty_input_returns_empty_assignment():
    result = leakage_safe_split([], ratios={"train": 0.8, "val": 0.1, "test": 0.1})
    assert result.split_by_video_id == {}
    assert result.counts == {}


def test_ratios_must_sum_to_one():
    with pytest.raises(ValueError):
        leakage_safe_split(_units(5), ratios={"train": 0.8, "val": 0.1})


def test_ratios_must_be_non_negative():
    with pytest.raises(ValueError):
        leakage_safe_split(_units(5), ratios={"train": 1.2, "val": -0.2})


def test_split_is_deterministic_for_the_same_seed():
    units = _units(50)
    first = leakage_safe_split(units, ratios={"train": 0.7, "val": 0.15, "test": 0.15}, seed=42)
    second = leakage_safe_split(units, ratios={"train": 0.7, "val": 0.15, "test": 0.15}, seed=42)
    assert first.split_by_video_id == second.split_by_video_id


def test_different_seeds_can_produce_different_assignments():
    units = _units(50)
    first = leakage_safe_split(units, ratios={"train": 0.5, "val": 0.5}, seed=1)
    second = leakage_safe_split(units, ratios={"train": 0.5, "val": 0.5}, seed=2)
    assert first.split_by_video_id != second.split_by_video_id


def test_realized_sizes_track_requested_ratios_closely():
    units = _units(100)
    result = leakage_safe_split(units, ratios={"train": 0.8, "val": 0.1, "test": 0.1}, seed=7)
    assert result.counts["train"] == pytest.approx(80, abs=2)
    assert result.counts["val"] == pytest.approx(10, abs=2)
    assert result.counts["test"] == pytest.approx(10, abs=2)
    assert sum(result.counts.values()) == 100


def test_multiple_videos_sharing_a_group_never_split_across_sets():
    """The actual leakage scenario this module exists to prevent: two
    camera-angle videos of the *same match* must always land in the same
    split, even though they have different video_ids."""
    units = [
        SplitUnit(video_id="match1-cam1", group_key="match1"),
        SplitUnit(video_id="match1-cam2", group_key="match1"),
        *_units(20, group_prefix="other-match"),
    ]
    result = leakage_safe_split(units, ratios={"train": 0.7, "val": 0.15, "test": 0.15}, seed=3)
    assert result.split_by_video_id["match1-cam1"] == result.split_by_video_id["match1-cam2"]
    assert detect_cross_split_group_leakage(result) == []


def test_default_group_key_is_the_video_id_itself():
    unit = SplitUnit(video_id="v1")
    assert unit.group_key == "v1"


def test_weighted_split_accounts_for_group_weight_not_just_group_count():
    # One huge match (weight 90) and nine tiny ones (weight 1 each, total 9)
    # -- an unweighted split would put the huge match entirely in one
    # bucket and badly blow the target ratio for that bucket's *content*
    # volume, even if the *group count* ratio looked fine.
    units = [SplitUnit(video_id="big", group_key="big", weight=90.0)] + [
        SplitUnit(video_id=f"small-{i}", group_key=f"small-{i}", weight=1.0) for i in range(9)
    ]
    result = leakage_safe_split(units, ratios={"train": 0.8, "val": 0.2}, seed=5)
    # The big match's own split must hold at least most of the weight-80 target.
    big_split = result.split_by_video_id["big"]
    assert result.counts[big_split] >= 1


def test_detect_cross_split_group_leakage_is_clean_for_a_real_assignment():
    units = [
        SplitUnit(video_id="match1-cam1", group_key="match1"),
        SplitUnit(video_id="match1-cam2", group_key="match1"),
        *_units(10, group_prefix="other-match"),
    ]
    result = leakage_safe_split(units, ratios={"train": 0.8, "val": 0.2}, seed=9)
    assert detect_cross_split_group_leakage(result) == []


def test_existing_assignment_pins_prior_groups_when_the_dataset_grows():
    """The exact reproduction from TECH_DEBT.md: 10 videos split 60/20/20
    with seed=42, then 2 more videos added with the same seed. Without
    existing_assignment, most of the original 10 reshuffle. With it, the
    original 10 must be byte-for-byte unchanged and only the 2 new videos
    get placed."""
    ratios = {"train": 0.6, "val": 0.2, "test": 0.2}
    original_units = _units(10)
    original = leakage_safe_split(original_units, ratios=ratios, seed=42)

    grown_units = original_units + [
        SplitUnit(video_id="video-10", group_key="match-10"),
        SplitUnit(video_id="video-11", group_key="match-11"),
    ]

    # Sanity check the bug actually reproduces without the fix engaged.
    naive_regrown = leakage_safe_split(grown_units, ratios=ratios, seed=42)
    reshuffled = [
        v
        for v in original.split_by_video_id
        if naive_regrown.split_by_video_id[v] != original.split_by_video_id[v]
    ]
    assert reshuffled, "expected the naive re-split to reproduce the known reshuffle bug"

    pinned_regrown = leakage_safe_split(
        grown_units, ratios=ratios, seed=42, existing_assignment=original
    )
    for video_id, split in original.split_by_video_id.items():
        assert pinned_regrown.split_by_video_id[video_id] == split
    assert "video-10" in pinned_regrown.split_by_video_id
    assert "video-11" in pinned_regrown.split_by_video_id
    assert detect_cross_split_group_leakage(pinned_regrown) == []


def test_existing_assignment_keeps_a_pinned_group_together_when_it_gains_a_video():
    """A group that grows a second video (e.g. a second camera angle added
    to an already-split match) must stay pinned to its existing split as a
    whole, not just the video_ids that existed at pin time."""
    ratios = {"train": 0.5, "val": 0.5}
    original = leakage_safe_split(
        [SplitUnit(video_id="match1-cam1", group_key="match1")], ratios=ratios, seed=1
    )
    original_split = original.split_by_video_id["match1-cam1"]

    grown = leakage_safe_split(
        [
            SplitUnit(video_id="match1-cam1", group_key="match1"),
            SplitUnit(video_id="match1-cam2", group_key="match1"),
        ],
        ratios=ratios,
        seed=1,
        existing_assignment=original,
    )
    assert grown.split_by_video_id["match1-cam1"] == original_split
    assert grown.split_by_video_id["match1-cam2"] == original_split


def test_existing_assignment_rejects_a_pin_to_a_split_no_longer_offered():
    original = leakage_safe_split(_units(3), ratios={"train": 0.7, "val": 0.3}, seed=1)
    with pytest.raises(ValueError, match="not one of the requested ratios"):
        leakage_safe_split(
            _units(3) + [SplitUnit(video_id="video-3", group_key="match-3")],
            ratios={"train": 0.5, "holdout": 0.5},
            seed=1,
            existing_assignment=original,
        )


def test_detect_cross_split_group_leakage_flags_a_hand_corrupted_assignment():
    """Simulates the real corruption this function exists to catch: after
    a valid split, someone hand-edits split_by_video_id to move one video
    to a different split without moving its group-mate -- e.g. a well-
    meaning but leakage-unaware manual reassignment of a single clip."""
    units = [
        SplitUnit(video_id="match1-cam1", group_key="match1"),
        SplitUnit(video_id="match1-cam2", group_key="match1"),
    ]
    result = leakage_safe_split(units, ratios={"train": 1.0}, seed=1)
    assert result.split_by_video_id["match1-cam1"] == "train"

    from dataclasses import replace

    corrupted_split_by_video_id = dict(result.split_by_video_id)
    corrupted_split_by_video_id["match1-cam2"] = "test"  # moved without its group-mate
    corrupted = replace(result, split_by_video_id=corrupted_split_by_video_id)

    leaking_groups = detect_cross_split_group_leakage(corrupted)
    assert leaking_groups == ["match1"]
