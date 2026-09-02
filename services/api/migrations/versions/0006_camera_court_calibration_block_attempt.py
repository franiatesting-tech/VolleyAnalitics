"""add camera_segments, court_calibrations, block_attempts

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "camera_segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("index_in_video", sa.Integer(), nullable=False),
        sa.Column("video_t_start", sa.Float(), nullable=False),
        sa.Column("video_t_end", sa.Float(), nullable=True),
        sa.Column("shot_type", sa.String(length=16), nullable=False),
        sa.Column("tactical_usable", sa.String(length=12), nullable=False),
        sa.Column("model_run_id", sa.String(length=36), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_id", "index_in_video", name="uq_camera_segment_video_index"),
    )
    op.create_index("ix_camera_segments_video_id", "camera_segments", ["video_id"])

    op.create_table(
        "court_calibrations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("camera_segment_id", sa.String(length=36), nullable=False),
        sa.Column("method", sa.String(length=24), nullable=False),
        sa.Column("homography_matrix", sa.JSON(), nullable=False),
        sa.Column("keypoints", sa.JSON(), nullable=True),
        sa.Column("reprojection_error_px", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("model_run_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["camera_segment_id"], ["camera_segments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_court_calibrations_camera_segment_id",
        "court_calibrations",
        ["camera_segment_id"],
    )

    op.create_table(
        "block_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("rally_id", sa.String(length=36), nullable=False),
        sa.Column("actor_roster_id", sa.String(length=36), nullable=True),
        sa.Column("actor_team_id", sa.String(length=36), nullable=False),
        sa.Column("video_t", sa.Float(), nullable=False),
        sa.Column("court_x", sa.Float(), nullable=False),
        sa.Column("court_y", sa.Float(), nullable=False),
        sa.Column("block_mode", sa.String(length=16), nullable=False),
        sa.Column("block_role", sa.String(length=16), nullable=False),
        sa.Column("jumped", sa.Boolean(), nullable=True),
        sa.Column("action_id", sa.String(length=36), nullable=True),
        sa.Column("model_run_id", sa.String(length=36), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["rally_id"], ["rallies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_roster_id"], ["rosters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["action_id"], ["actions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_block_attempts_rally_id", "block_attempts", ["rally_id"])


def downgrade() -> None:
    op.drop_index("ix_block_attempts_rally_id", table_name="block_attempts")
    op.drop_table("block_attempts")
    op.drop_index("ix_court_calibrations_camera_segment_id", table_name="court_calibrations")
    op.drop_table("court_calibrations")
    op.drop_index("ix_camera_segments_video_id", table_name="camera_segments")
    op.drop_table("camera_segments")
