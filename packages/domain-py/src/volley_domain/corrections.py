"""Human correction/review recording -- see docs/domain/ONTOLOGY.md's
"Correction semantics" section. These functions only ever INSERT; neither
ever updates or deletes an existing HumanCorrection/ReviewedLabel row, and
neither touches the target row's own columns (e.g. Action.action_type) --
that's the caller's job, deliberately kept separate (see module docstring
below) so this module can't accidentally make a correction destroy the
prediction it corrects.
"""

from sqlalchemy.orm import Session

from volley_domain.ontology import (
    CorrectionTargetType,
    HumanCorrection,
    ReviewedLabel,
    ReviewStatus,
)


def record_correction(
    db: Session,
    *,
    target_type: CorrectionTargetType,
    target_id: str,
    field_name: str,
    previous_value: dict,
    corrected_value: dict,
    corrected_by_user_id: str,
    reason: str | None = None,
) -> HumanCorrection:
    """Inserts one append-only HumanCorrection row. Does NOT update the
    target row itself (e.g. an Action's `action_type` column) -- that's a
    separate, deliberate step for the caller, so "record that a correction
    happened" and "apply the corrected value to the row ordinary reads see"
    can never be silently conflated into one operation that might skip the
    audit trail under a bug. A typical caller does both in the same
    transaction:

        record_correction(db, target_type=CorrectionTargetType.ACTION, ...)
        action.action_type = new_value
        db.commit()
    """
    correction = HumanCorrection(
        target_type=target_type,
        target_id=target_id,
        field_name=field_name,
        previous_value=previous_value,
        corrected_value=corrected_value,
        corrected_by_user_id=corrected_by_user_id,
        reason=reason,
    )
    db.add(correction)
    return correction


def record_review(
    db: Session,
    *,
    target_type: CorrectionTargetType,
    target_id: str,
    reviewed_by_user_id: str,
    status: ReviewStatus,
    notes: str | None = None,
) -> ReviewedLabel:
    """Inserts one ReviewedLabel row. A CONFIRMED review with no
    accompanying `record_correction` call means "a human looked at this
    prediction and it was already right" -- not every review is a
    correction, per ONTOLOGY.md."""
    label = ReviewedLabel(
        target_type=target_type,
        target_id=target_id,
        reviewed_by_user_id=reviewed_by_user_id,
        status=status,
        notes=notes,
    )
    db.add(label)
    return label


def correction_history(
    db: Session, *, target_type: CorrectionTargetType, target_id: str
) -> list[HumanCorrection]:
    """Every correction ever recorded for a target, oldest first -- the
    oldest row's `previous_value` is what the model originally predicted,
    per ONTOLOGY.md's reconstruction guarantee."""
    return list(
        db.query(HumanCorrection)
        .filter(
            HumanCorrection.target_type == target_type,
            HumanCorrection.target_id == target_id,
        )
        .order_by(HumanCorrection.corrected_at.asc())
        .all()
    )
