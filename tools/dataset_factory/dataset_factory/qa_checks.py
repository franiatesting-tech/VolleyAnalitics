"""QA checks for an annotated dataset -- schema validity, label
distribution, and missing-field detection, run against
`volley_domain.annotation`'s normalized shapes (already converted from
CVAT/FiftyOne exports -- see cvat_import.py). Pure logic, no live CVAT/
FiftyOne/network dependency, so this can run in CI against any exported
manifest.

This is deliberately NOT a replacement for `volley_domain.dataset_split`'s
`detect_cross_split_group_leakage` (a distinct, already-covered concern) --
`run_qa` accepts an optional `SplitAssignment` and calls that check too, so
a single QA report command surfaces both problem classes together, but the
leakage logic itself isn't duplicated here.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError
from volley_domain.annotation import PlayerBBoxAnnotation
from volley_domain.dataset_split import SplitAssignment, detect_cross_split_group_leakage


@dataclass
class SchemaError:
    source_file: str
    record_index: int
    message: str


@dataclass(frozen=True)
class QAPolicy:
    min_valid_records: int = 1
    max_missing_fraction_by_field: dict[str, float] = field(
        default_factory=lambda: {"team": 0.0, "position": 0.2, "jersey_number": 0.2}
    )


@dataclass
class QAReport:
    total_records: int
    valid_records: int
    schema_errors: list[SchemaError] = field(default_factory=list)
    label_distribution: dict[str, dict[str, int]] = field(default_factory=dict)
    missing_field_counts: dict[str, int] = field(default_factory=dict)
    leaking_groups: list[str] = field(default_factory=list)
    policy_violations: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.schema_errors and not self.leaking_groups and not self.policy_violations

    def summary_text(self) -> str:
        lines = [
            f"Records: {self.valid_records}/{self.total_records} valid",
            f"Schema errors: {len(self.schema_errors)}",
            f"Cross-split leaking groups: {len(self.leaking_groups)}",
            f"Policy violations: {len(self.policy_violations)}",
        ]
        for field_name, count in sorted(self.missing_field_counts.items()):
            lines.append(f"Missing '{field_name}': {count}")
        for dimension, counts in self.label_distribution.items():
            lines.append(f"Distribution by {dimension}:")
            for value, count in sorted(counts.items(), key=lambda kv: -kv[1]):
                lines.append(f"  {value}: {count}")
        for violation in self.policy_violations:
            lines.append(f"Policy: {violation}")
        return "\n".join(lines)


def load_player_bbox_annotations_from_json(
    path: Path,
) -> tuple[list[PlayerBBoxAnnotation], list[SchemaError]]:
    """Loads a JSON array of annotation records (the on-disk export shape
    this project's CVAT/FiftyOne import scripts produce). Each record is
    independently validated -- one malformed annotation doesn't abort the
    whole file's load, it's collected as a SchemaError and the rest still
    load, so a QA run against a batch of hundreds of annotations reports
    every problem in one pass instead of stopping at the first."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a JSON array of annotation records")

    valid: list[PlayerBBoxAnnotation] = []
    errors: list[SchemaError] = []
    for index, record in enumerate(raw):
        try:
            valid.append(PlayerBBoxAnnotation.model_validate(record))
        except ValidationError as exc:
            errors.append(SchemaError(source_file=str(path), record_index=index, message=str(exc)))
    return valid, errors


def run_qa(
    annotations: list[PlayerBBoxAnnotation],
    *,
    schema_errors: list[SchemaError] | None = None,
    split_assignment: SplitAssignment | None = None,
    policy: QAPolicy | None = None,
) -> QAReport:
    schema_errors = schema_errors or []
    total = len(annotations) + len(schema_errors)

    team_counts: Counter[str] = Counter()
    position_counts: Counter[str] = Counter()
    missing_team = 0
    missing_position = 0
    missing_jersey = 0

    for ann in annotations:
        team_counts[ann.team or "(missing)"] += 1
        position_counts[(ann.position.value if ann.position else "(missing)")] += 1
        if ann.team is None:
            missing_team += 1
        if ann.position is None:
            missing_position += 1
        if ann.jersey_number is None:
            missing_jersey += 1

    leaking_groups = detect_cross_split_group_leakage(split_assignment) if split_assignment else []
    policy = policy or QAPolicy()
    missing_counts = {
        "team": missing_team,
        "position": missing_position,
        "jersey_number": missing_jersey,
    }
    policy_violations: list[str] = []
    if len(annotations) < policy.min_valid_records:
        policy_violations.append(
            f"valid record count {len(annotations)} is below minimum {policy.min_valid_records}"
        )
    for field_name, maximum in policy.max_missing_fraction_by_field.items():
        count = missing_counts.get(field_name, 0)
        fraction = count / len(annotations) if annotations else 1.0
        if fraction > maximum:
            policy_violations.append(
                f"missing {field_name} fraction {fraction:.3f} exceeds {maximum:.3f}"
            )

    return QAReport(
        total_records=total,
        valid_records=len(annotations),
        schema_errors=schema_errors,
        label_distribution={"team": dict(team_counts), "position": dict(position_counts)},
        missing_field_counts=missing_counts,
        leaking_groups=leaking_groups,
        policy_violations=policy_violations,
    )


def run_qa_on_directory(
    directory: Path,
    *,
    glob_pattern: str = "*_annotations.json",
    split_assignment: SplitAssignment | None = None,
    policy: QAPolicy | None = None,
) -> QAReport:
    """`glob_pattern` defaults to files explicitly named `*_annotations.json`
    rather than a bare `*.json` -- a real dataset-factory output directory
    also holds split manifests, dataset cards, etc. as JSON, and globbing
    everything would try (and fail) to parse those as annotation records.
    Callers with a different naming convention should pass their own
    pattern explicitly rather than relying on this default."""
    all_annotations: list[PlayerBBoxAnnotation] = []
    all_errors: list[SchemaError] = []
    for json_file in sorted(directory.glob(glob_pattern)):
        annotations, errors = load_player_bbox_annotations_from_json(json_file)
        all_annotations.extend(annotations)
        all_errors.extend(errors)
    return run_qa(
        all_annotations,
        schema_errors=all_errors,
        split_assignment=split_assignment,
        policy=policy,
    )
