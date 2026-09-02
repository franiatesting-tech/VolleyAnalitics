"""align court_calibrations with CameraCalibrationAnnotation, fix block_attempts provenance

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-31

All three tables touched here (camera_segments, court_calibrations,
block_attempts) were added in 0006 and are verified empty in every
environment this has been applied to (0/0/0 rows) -- this migration uses
ALTER, not a destructive drop/recreate, so it's safe regardless, but is
only ever meant to run immediately after 0006 with no real data in
between. See TECH_DEBT.md's "CameraSegment/CourtCalibration/BlockAttempt"
entry for the independent architecture review that found these gaps.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # court_calibrations: align with volley_domain.annotation.CameraCalibrationAnnotation
    # (image dimensions, Phase-B metric-3D fields, manual-recalibration audit
    # columns) -- see CourtCalibration's own docstring for the full reasoning.
    op.add_column(
        "court_calibrations",
        sa.Column("image_width", sa.Integer(), nullable=False, server_default="1280"),
    )
    op.add_column(
        "court_calibrations",
        sa.Column("image_height", sa.Integer(), nullable=False, server_default="720"),
    )
    op.alter_column("court_calibrations", "image_width", server_default=None)
    op.alter_column("court_calibrations", "image_height", server_default=None)
    op.add_column("court_calibrations", sa.Column("camera_matrix", sa.JSON(), nullable=True))
    op.add_column(
        "court_calibrations", sa.Column("rotation_world_to_camera", sa.JSON(), nullable=True)
    )
    op.add_column(
        "court_calibrations", sa.Column("translation_world_to_camera_m", sa.JSON(), nullable=True)
    )
    op.add_column(
        "court_calibrations",
        sa.Column("supports_metric_3d", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("court_calibrations", "supports_metric_3d", server_default=None)
    op.add_column(
        "court_calibrations", sa.Column("created_by_user_id", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "court_calibrations",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )

    # block_attempts: model_run_id/confidence become required, matching
    # Action's own provenance requirement -- see BlockAttempt's docstring.
    op.execute(
        "DELETE FROM block_attempts"
    )  # no-op if empty; guards against a real NOT NULL failure
    op.alter_column("block_attempts", "model_run_id", nullable=False)
    op.alter_column("block_attempts", "confidence", nullable=False)
    op.drop_constraint("block_attempts_model_run_id_fkey", "block_attempts", type_="foreignkey")
    op.create_foreign_key(
        "block_attempts_model_run_id_fkey",
        "block_attempts",
        "model_runs",
        ["model_run_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("block_attempts_model_run_id_fkey", "block_attempts", type_="foreignkey")
    op.create_foreign_key(
        "block_attempts_model_run_id_fkey",
        "block_attempts",
        "model_runs",
        ["model_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("block_attempts", "confidence", nullable=True)
    op.alter_column("block_attempts", "model_run_id", nullable=True)

    op.drop_column("court_calibrations", "superseded_at")
    op.drop_column("court_calibrations", "created_by_user_id")
    op.drop_column("court_calibrations", "supports_metric_3d")
    op.drop_column("court_calibrations", "translation_world_to_camera_m")
    op.drop_column("court_calibrations", "rotation_world_to_camera")
    op.drop_column("court_calibrations", "camera_matrix")
    op.drop_column("court_calibrations", "image_height")
    op.drop_column("court_calibrations", "image_width")
