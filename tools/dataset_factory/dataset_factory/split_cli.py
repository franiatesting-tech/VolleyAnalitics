"""CLI wrapper around volley_domain.dataset_split.leakage_safe_split.
Reads a JSON video inventory manifest, writes a JSON split-assignment
manifest (intended to be DVC-tracked so the exact split for a dataset
version is frozen and reproducible -- see cv-experiment/ml-evaluation
skills' "same frozen dataset version" requirement).

Usage:
    uv run python -m dataset_factory.split_cli \\
        --inventory inventory.json --ratios train=0.8,val=0.1,test=0.1 \\
        --seed 42 --out split.json

    # Growing an already-frozen dataset: pass its previous split.json so
    # every already-assigned group is pinned to its prior split (see
    # leakage_safe_split's `existing_assignment` docstring for why this is
    # required, not optional, once a split has been used for any real
    # evaluation) --
    uv run python -m dataset_factory.split_cli \\
        --inventory inventory.json --ratios train=0.8,val=0.1,test=0.1 \\
        --seed 42 --existing previous-split.json --out split.json

inventory.json shape: a JSON array of
{"video_id": "...", "group_key": "...", "weight": 1.0}
(group_key/weight optional -- see SplitUnit's own defaults).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from volley_domain.dataset_split import (
    SplitAssignment,
    SplitUnit,
    detect_cross_split_group_leakage,
    leakage_safe_split,
)


def _parse_ratios(raw: str) -> dict[str, float]:
    ratios: dict[str, float] = {}
    for part in raw.split(","):
        name, _, value = part.partition("=")
        if not name or not value:
            raise ValueError(f"Malformed ratio segment: {part!r} (expected name=fraction)")
        ratios[name.strip()] = float(value)
    return ratios


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--ratios", type=str, required=True, help="e.g. train=0.8,val=0.1,test=0.1")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--existing",
        type=Path,
        default=None,
        help=(
            "Previous split.json (this CLI's own --out format) to pin already-"
            "assigned groups against, so growing the dataset can't reshuffle a "
            "split anyone has already evaluated against -- see "
            "leakage_safe_split's existing_assignment docstring."
        ),
    )
    args = parser.parse_args(argv)

    inventory_raw = json.loads(args.inventory.read_text(encoding="utf-8"))
    units = [SplitUnit(**entry) for entry in inventory_raw]
    ratios = _parse_ratios(args.ratios)

    existing_assignment: SplitAssignment | None = None
    if args.existing is not None:
        existing_raw = json.loads(args.existing.read_text(encoding="utf-8"))
        existing_assignment = SplitAssignment(
            split_by_video_id=existing_raw["split_by_video_id"],
            group_key_by_video_id=existing_raw["group_key_by_video_id"],
            counts=existing_raw.get("counts", {}),
        )

    assignment = leakage_safe_split(
        units, ratios=ratios, seed=args.seed, existing_assignment=existing_assignment
    )
    leaking = detect_cross_split_group_leakage(assignment)
    if leaking:
        # Should be unreachable (leakage_safe_split's own output is always
        # leak-free by construction) -- a hit here means a real bug in this
        # module, not a data problem, so fail loud rather than write a
        # manifest that looks fine but silently leaks.
        print(
            f"INTERNAL ERROR: leakage_safe_split produced leaking groups: {leaking}",
            file=sys.stderr,
        )
        return 1

    args.out.write_text(
        json.dumps(
            {
                "seed": args.seed,
                "ratios": ratios,
                "split_by_video_id": assignment.split_by_video_id,
                "group_key_by_video_id": assignment.group_key_by_video_id,
                "counts": assignment.counts,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote split assignment for {len(units)} video(s) to {args.out}")
    print(f"Counts: {assignment.counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
