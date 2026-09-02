"""Formal schema and validation for a clip pool's manual visual-QA report
(golden-v0's VISUAL_QA.json), replacing a free-text, unvalidated JSON file
with a controlled vocabulary -- specifically so that non-representative
footage (warm-ups, court cleaning, ceremonies, timeouts) has an explicit,
checkable category rather than being caught only if a reviewer happens to
mention it in free text. See PROFESSIONAL_ANNOTATION_PROTOCOL.md's rally-
boundary rule ("Timeouts, substitutions, warm-ups and empty-court
transitions are negative segments, not rallies") -- this module is the
*clip-selection-time* counterpart of that rule: catching non-representative
footage before it ever enters the annotation pipeline, not just excluding
it from rally boundaries after the fact.

This does not attempt automatic (pixel-based) warm-up/cleaning detection --
that needs its own training data this project does not have yet (the same
bootstrapping problem as role detection, see jersey_color.py's docstring).
It formalizes the *human* (or AI-reviewer, acting as a human's stand-in and
still subject to the same accountability) visual-review step so it is
consistent, complete and auditable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Every reason a clip candidate might be rejected before ever entering the
# frozen pool. "other" exists but must carry a real explanation in `notes`
# -- it is not an escape hatch for skipping the other categories' judgment.
RejectionReason = Literal[
    "warmup",
    "pregame_ceremony",
    "court_cleaning_or_maintenance",
    "timeout_or_stoppage",
    "celebration_or_dead_time",
    "camera_transition_or_broadcast_cutaway",
    "low_active_play_density",
    "other",
]

AcceptedDecision = Literal["accepted_active_play", "accepted_transition_negative"]


class AcceptedClipReview(BaseModel):
    clip_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,79}$")
    decision: AcceptedDecision
    notes: str = Field(min_length=1)


class RejectedInterval(BaseModel):
    source_video_id: str = Field(min_length=1)
    segment_start_seconds: float = Field(ge=0)
    reason: RejectionReason
    notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def _other_reason_needs_real_explanation(self) -> RejectedInterval:
        if self.reason == "other" and len(self.notes.strip()) < 15:
            raise ValueError(
                "reason='other' requires a substantive explanation in notes "
                "(at least 15 characters) -- 'other' is not a shortcut past "
                "picking a real category"
            )
        return self


class VisualQAReport(BaseModel):
    dataset_version: str = Field(min_length=1)
    performed_at: str = Field(min_length=1)
    method: str = Field(min_length=1)
    clips: list[AcceptedClipReview] = Field(min_length=1)
    rejected_intervals: list[RejectedInterval] = Field(default_factory=list)
    result: Literal["accepted_for_annotation_and_unlabelled_pretraining", "blocked"]

    @model_validator(mode="after")
    def _clip_ids_are_unique(self) -> VisualQAReport:
        # `clips: list[...] = Field(min_length=1)` above already guarantees
        # at least one accepted clip whenever `result` claims acceptance --
        # nothing further to check for that case here.
        clip_ids = [clip.clip_id for clip in self.clips]
        if len(clip_ids) != len(set(clip_ids)):
            raise ValueError("clip_id values in 'clips' must be unique")
        return self

    @property
    def active_play_count(self) -> int:
        return sum(1 for clip in self.clips if clip.decision == "accepted_active_play")

    @property
    def transition_negative_count(self) -> int:
        return sum(1 for clip in self.clips if clip.decision == "accepted_transition_negative")


def load_visual_qa_report(path: Path) -> VisualQAReport:
    return VisualQAReport.model_validate_json(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    report = load_visual_qa_report(args.report)
    print(
        json.dumps(
            {
                "valid": True,
                "accepted_clip_count": len(report.clips),
                "active_play_count": report.active_play_count,
                "transition_negative_count": report.transition_negative_count,
                "rejected_interval_count": len(report.rejected_intervals),
                "rejected_reasons": sorted({r.reason for r in report.rejected_intervals}),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
