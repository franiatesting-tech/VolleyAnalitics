"""add video_detection_frames and pipeline_runs.error

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-31

Backs the exploratory per-frame RF-DETR detection pipeline for real
uploaded videos -- see VideoDetectionFrame's docstring in ontology.py for
why this is a separate table from PlayerObservation (no calibrated court
coordinates exist for real footage yet). `pipeline_runs.error` mirrors
ProcessingJob.error so a FAILED detection run can explain why without a
human digging through worker logs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pipeline_runs", sa.Column("error", sa.Text(), nullable=True))

    op.create_table(
        "video_detection_frames",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "video_id",
            sa.String(length=36),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "model_run_id",
            sa.String(length=36),
            sa.ForeignKey("model_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("timestamp_seconds", sa.Float(), nullable=False),
        sa.Column("detections", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("model_run_id", "frame_index", name="uq_detection_frame_run_index"),
    )
    op.create_index("ix_video_detection_frames_video_id", "video_detection_frames", ["video_id"])
    op.create_index(
        "ix_video_detection_frames_model_run_id", "video_detection_frames", ["model_run_id"]
    )
    op.create_index(
        "ix_video_detection_frames_timestamp_seconds",
        "video_detection_frames",
        ["timestamp_seconds"],
    )


def downgrade() -> None:
    op.drop_index("ix_video_detection_frames_timestamp_seconds", "video_detection_frames")
    op.drop_index("ix_video_detection_frames_model_run_id", "video_detection_frames")
    op.drop_index("ix_video_detection_frames_video_id", "video_detection_frames")
    op.drop_table("video_detection_frames")
    op.drop_column("pipeline_runs", "error")
