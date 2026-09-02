"""Leakage-safe train/val/test splitting for CV datasets built from match
video. The specific bug this exists to prevent: splitting at the level of
individual frames or clips lets near-duplicate/adjacent frames from the
*same rally* (often near-identical -- a player mid-swing one frame apart)
land in different splits, and splitting at the rally level without
grouping by match lets the *same match* (same lighting, camera angle,
jerseys, court, crowd) appear in both train and test, inflating validation
metrics on information the model implicitly memorized rather than
generalizing from. Both are well-documented, common CV dataset bugs -- see
the `cv-experiment`/`ml-evaluation` skills' "same frozen dataset version"
and "evaluated on a set the model never saw" requirements, which only mean
anything if the split itself doesn't leak in the first place.

The unit of assignment is always the **video** (a full source video, e.g.
one full match or one half) -- every rally/clip/frame from a given video_id
goes to exactly one split. This is coarser than rally-level or frame-level
splitting, deliberately: it's the only grouping granularity that can't leak
regardless of how downstream sampling (frames, clips, rallies) is done,
without needing that downstream code to *also* know the leakage rules.

Pure, deterministic, no I/O -- callers assemble a `list[SplitUnit]` from
whatever inventory of videos/matches exists (in this project, `Video`/
`Match` rows or a manifest file; not read by this module directly) and get
back deterministic split assignments for a given seed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

SplitName = str  # "train" | "val" | "test", but callers may name splits differently


@dataclass(frozen=True)
class SplitUnit:
    """One video's worth of leakage-relevant identity. `group_key`
    defaults to `video_id` but can be overridden to something coarser --
    e.g. multiple camera angles/halves of the *same physical match* should
    share a `group_key` (the match id) so they can never be split apart
    across train/test even though they're different `video_id`s."""

    video_id: str
    group_key: str = ""
    weight: float = 1.0  # e.g. rally count or duration, for proportional splitting

    def __post_init__(self):
        if not self.group_key:
            object.__setattr__(self, "group_key", self.video_id)


@dataclass(frozen=True)
class SplitAssignment:
    split_by_video_id: dict[str, SplitName]
    # Preserved (not just split_by_group's group->split summary) so
    # detect_cross_split_group_leakage can genuinely re-derive leakage
    # independently from split_by_video_id alone, rather than trusting
    # this module's own bookkeeping -- see that function's docstring.
    group_key_by_video_id: dict[str, str]
    counts: dict[SplitName, int] = field(default_factory=dict)


def _stable_hash_fraction(key: str, seed: int) -> float:
    """Deterministic, seed-dependent pseudo-random value in [0, 1) for a
    group key -- SHA-256-based rather than `random.Random` so the exact
    same (key, seed) always produces the exact same fraction regardless of
    call order or platform, which is what "the same frozen dataset version"
    (cv-experiment skill) actually requires: re-running the split script
    against the same inventory must reproduce the identical assignment."""
    digest = hashlib.sha256(f"{seed}:{key}".encode()).digest()
    as_int = int.from_bytes(digest[:8], "big")
    return as_int / 2**64


def leakage_safe_split(
    units: list[SplitUnit],
    *,
    ratios: dict[SplitName, float],
    seed: int = 0,
    existing_assignment: SplitAssignment | None = None,
) -> SplitAssignment:
    """Assigns every unique `group_key` among `units` to exactly one split,
    then propagates that assignment to every `video_id` sharing the group
    -- so no group (match/video family) is ever split across train/val/test.

    Deterministic given (units, ratios, seed): re-running against the same
    inventory always reproduces the same assignment, which is what makes a
    split "frozen" in the DVC-pinned sense the cv-experiment/ml-evaluation
    skills require -- not just "we didn't intentionally change it."

    Splitting is weighted by each group's total `weight` (summed across its
    units) using each group's stable hash fraction against the *cumulative*
    weight-normalized ratio boundaries, not a per-group coin flip against
    fixed ratios -- a coin flip only converges to the target ratios in
    expectation over many groups, and this project explicitly wants "a
    small, high-quality golden dataset" first (few groups), where that
    convergence assumption doesn't hold. Deterministic boundary assignment
    guarantees the *realized* split sizes track the requested ratios
    exactly (up to one group's weight of rounding) even with just a
    handful of groups.

    `existing_assignment`, when given, **pins every already-assigned
    group** to its prior split before any new groups are placed -- this is
    what makes growing a frozen dataset safe. Without it, adding even one
    new group can silently reshuffle most of a previously-frozen split:
    the greedy fill's ordering is stable per group, but a new group can
    land anywhere in that order, and `total_weight` (hence every target)
    changes too, so essentially every downstream assignment decision can
    differ even though the *code* didn't change. Reproduced directly
    (TECH_DEBT.md, 2026-08-29): 10 videos split 60/20/20 with seed=42, then
    2 more added with the same seed -- 8 of the original 10 moved splits,
    2 of them crossing from `test` into `train`, silently invalidating any
    evaluation already run against the old split. With `existing_assignment`
    passed on the second call, only the 2 new groups get placed; the
    original 10 videos' splits are byte-for-byte unchanged.
    """
    if not units:
        return SplitAssignment(split_by_video_id={}, group_key_by_video_id={})
    if abs(sum(ratios.values()) - 1.0) > 1e-6:
        raise ValueError(f"ratios must sum to 1.0, got {sum(ratios.values())}")
    if any(r < 0 for r in ratios.values()):
        raise ValueError("ratios must be non-negative")

    group_weight: dict[str, float] = {}
    group_videos: dict[str, list[str]] = {}
    for unit in units:
        group_weight[unit.group_key] = group_weight.get(unit.group_key, 0.0) + unit.weight
        group_videos.setdefault(unit.group_key, []).append(unit.video_id)

    # Pin every group the caller already froze in a prior split, keyed by
    # *this* call's group_key (not the prior call's -- a video's group_key
    # is caller-supplied and must be consistent across calls for pinning
    # to mean anything, exactly like leakage detection already assumes).
    pinned_split_by_group: dict[str, SplitName] = {}
    if existing_assignment is not None:
        for video_id, split in existing_assignment.split_by_video_id.items():
            group = existing_assignment.group_key_by_video_id.get(video_id, video_id)
            if group in group_weight and group not in pinned_split_by_group:
                if split not in ratios:
                    raise ValueError(
                        f"existing_assignment pins group {group!r} to split {split!r}, "
                        f"which is not one of the requested ratios {sorted(ratios)!r}"
                    )
                pinned_split_by_group[group] = split

    total_weight = sum(group_weight.values())
    split_names = list(ratios.keys())

    # Sort groups by their stable hash fraction (deterministic, seed-
    # dependent order) and greedily fill each split up to its target
    # weight in that fixed order -- this is what makes realized sizes
    # track requested ratios closely even for a handful of groups, while
    # staying fully deterministic (no iterative rebalancing, no ties
    # broken by insertion order). Only *unpinned* (new) groups go through
    # this process; pinned groups keep their prior split untouched.
    unpinned_groups = [g for g in group_weight if g not in pinned_split_by_group]
    ordered_groups = sorted(unpinned_groups, key=lambda g: _stable_hash_fraction(g, seed))

    target_weight = {name: ratios[name] * total_weight for name in split_names}
    # Pinned groups' weight already counts against their split's target,
    # so new groups fill in around the frozen ones rather than pushing
    # every split's realized size past its ratio.
    filled_weight = dict.fromkeys(split_names, 0.0)
    for group, split in pinned_split_by_group.items():
        filled_weight[split] += group_weight[group]

    split_by_group: dict[str, SplitName] = dict(pinned_split_by_group)
    for group in ordered_groups:
        # Assign to whichever split is furthest below its target (as a
        # fraction of target) -- keeps every split proportionally on
        # track simultaneously instead of greedily overfilling the first
        # split in iteration order.
        def deficit(name: SplitName) -> float:
            target = target_weight[name]
            if target <= 0:
                return float("-inf")
            return (target - filled_weight[name]) / target

        chosen = max(split_names, key=deficit)
        split_by_group[group] = chosen
        filled_weight[chosen] += group_weight[group]

    split_by_video_id: dict[str, SplitName] = {}
    group_key_by_video_id: dict[str, str] = {}
    for group, video_ids in group_videos.items():
        for video_id in video_ids:
            split_by_video_id[video_id] = split_by_group[group]
            group_key_by_video_id[video_id] = group

    counts: dict[SplitName, int] = dict.fromkeys(split_names, 0)
    for name in split_by_video_id.values():
        counts[name] += 1

    return SplitAssignment(
        split_by_video_id=split_by_video_id,
        group_key_by_video_id=group_key_by_video_id,
        counts=counts,
    )


def detect_cross_split_group_leakage(assignment: SplitAssignment) -> list[str]:
    """Defense-in-depth: independently re-derives, from
    `split_by_video_id` + `group_key_by_video_id` alone, whether any group
    ended up spanning more than one split. Should always return `[]` for
    anything produced by `leakage_safe_split` itself unmodified -- this
    exists so a QA script (see tools/dataset_factory) can verify a split
    manifest that was hand-edited after the fact (e.g. one video
    reassigned to a different split without its group-mates), not just
    trust that the original assignment call was correct forever."""
    splits_by_group: dict[str, set[str]] = {}
    for video_id, split in assignment.split_by_video_id.items():
        group = assignment.group_key_by_video_id.get(video_id, video_id)
        splits_by_group.setdefault(group, set()).add(split)
    return [group for group, splits in splits_by_group.items() if len(splits) > 1]
