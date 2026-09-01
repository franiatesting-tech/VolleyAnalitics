"""add immutable professional rally analysis results

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rally_analysis_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=255), nullable=False),
        sa.Column("match_id", sa.String(length=36), nullable=False),
        sa.Column("rally_id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("bundle_data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rally_id"], ["rallies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rally_id",
            "pipeline_run_id",
            "schema_version",
            name="uq_rally_analysis_pipeline_schema",
        ),
    )
    op.create_index("ix_rally_analysis_results_match_id", "rally_analysis_results", ["match_id"])
    op.create_index(
        "ix_rally_analysis_results_organization_id",
        "rally_analysis_results",
        ["organization_id"],
    )
    op.create_index(
        "ix_rally_analysis_results_pipeline_run_id",
        "rally_analysis_results",
        ["pipeline_run_id"],
    )
    op.create_index("ix_rally_analysis_results_rally_id", "rally_analysis_results", ["rally_id"])
    op.create_index("ix_rally_analysis_results_video_id", "rally_analysis_results", ["video_id"])


def downgrade() -> None:
    op.drop_index("ix_rally_analysis_results_video_id", table_name="rally_analysis_results")
    op.drop_index("ix_rally_analysis_results_rally_id", table_name="rally_analysis_results")
    op.drop_index("ix_rally_analysis_results_pipeline_run_id", table_name="rally_analysis_results")
    op.drop_index("ix_rally_analysis_results_organization_id", table_name="rally_analysis_results")
    op.drop_index("ix_rally_analysis_results_match_id", table_name="rally_analysis_results")
    op.drop_table("rally_analysis_results")
