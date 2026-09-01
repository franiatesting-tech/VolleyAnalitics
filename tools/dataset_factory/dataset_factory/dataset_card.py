"""Dataset card generation -- documents provenance, licensing, and known
limitations for a DVC-tracked dataset version, matching the rigor
docs/domain/examples/README.md already applies to synthetic-vs-real
labeling elsewhere in this project (never let a reader assume more than
what's actually verified). See docs/datasets/DATASET_CARD_TEMPLATE.md for
the human-authorable version of the same shape this module renders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from volley_domain.dataset_split import SplitAssignment

from dataset_factory.qa_checks import QAReport


@dataclass
class DatasetCard:
    name: str
    dataset_version: str  # DVC-pinned version tag/hash this card describes
    description: str
    source_description: str  # where the raw video came from -- must be honest, see notes below
    license_notes: str
    created_at: datetime
    created_by: str
    split_counts: dict[str, int] = field(default_factory=dict)
    label_distribution: dict[str, dict[str, int]] = field(default_factory=dict)
    total_annotations: int = 0
    known_limitations: list[str] = field(default_factory=list)
    qa_clean: bool = False


def build_dataset_card(
    *,
    name: str,
    dataset_version: str,
    description: str,
    source_description: str,
    license_notes: str,
    created_by: str,
    qa_report: QAReport,
    split_assignment: SplitAssignment | None = None,
    known_limitations: list[str] | None = None,
) -> DatasetCard:
    return DatasetCard(
        name=name,
        dataset_version=dataset_version,
        description=description,
        source_description=source_description,
        license_notes=license_notes,
        created_at=datetime.now(),
        created_by=created_by,
        split_counts=dict(split_assignment.counts) if split_assignment else {},
        label_distribution=qa_report.label_distribution,
        total_annotations=qa_report.valid_records,
        known_limitations=known_limitations or [],
        qa_clean=qa_report.is_clean,
    )


def render_markdown(card: DatasetCard) -> str:
    lines = [
        f"# Dataset Card: {card.name}",
        "",
        f"**Version:** `{card.dataset_version}`  ",
        f"**Created:** {card.created_at.isoformat()} by {card.created_by}  ",
        f"**QA status:** {'clean' if card.qa_clean else 'HAS OPEN ISSUES -- see below'}",
        "",
        "## Description",
        "",
        card.description,
        "",
        "## Source & provenance",
        "",
        card.source_description,
        "",
        "## Licensing",
        "",
        card.license_notes,
        "",
        "## Splits",
        "",
    ]
    if card.split_counts:
        for split_name, count in sorted(card.split_counts.items()):
            lines.append(f"- **{split_name}**: {count} video(s)")
    else:
        lines.append("_No split assignment recorded for this card._")

    lines += ["", "## Label distribution", "", f"Total annotations: {card.total_annotations}", ""]
    for dimension, counts in card.label_distribution.items():
        lines.append(f"**By {dimension}:**")
        for value, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {value}: {count}")
        lines.append("")

    lines += ["## Known limitations", ""]
    if card.known_limitations:
        for limitation in card.known_limitations:
            lines.append(f"- {limitation}")
    else:
        lines.append("_None recorded._")

    return "\n".join(lines) + "\n"
