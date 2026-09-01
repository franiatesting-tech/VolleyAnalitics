"""videos: add width, height, start_time_seconds, time_base

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-30

Phase 4 (dataset factory / ingest pipeline), fix for a real gap caught by
independent architecture review: DATA_FLOW.md's "Video identity" section
requires "never key anything by frame number alone: every frame reference
carries original PTS/time ... and the mapping between them," but the
Phase 4 ingest pipeline as first shipped stored only `fps` (avg_frame_rate)
-- every ground-truth timestamp downstream would have been computed as
`frame_index / fps`, which is wrong for any variable-frame-rate source and
silently offset for any container with non-zero start_time (e.g.
MPEG-TS). Width/height were also missing despite
`annotation.py`'s CVAT-XML round-trip functions requiring them as
separate, easy-to-get-wrong caller-supplied arguments.

All four columns are nullable and additive -- no data loss, no narrowing.
Existing `videos` rows (there are none in any real environment yet) simply
have these fields unset until the next successful ingest run.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("videos", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column("videos", sa.Column("start_time_seconds", sa.Float(), nullable=True))
    op.add_column("videos", sa.Column("time_base", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "time_base")
    op.drop_column("videos", "start_time_seconds")
    op.drop_column("videos", "height")
    op.drop_column("videos", "width")
