"""videos: video_hash nullable, add error column

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-29

Phase 4 (dataset factory / ingest pipeline). Two changes to `videos`, both
additive/loosening (no data loss, no narrowing):

1. `video_hash` NOT NULL -> nullable. The Phase 4 ingest pipeline creates the
   `Video` row at upload-URL-issuance time (before any bytes exist to hash)
   so the client has a stable `video_id` to poll from the very first
   request; the worker fills in `video_hash` once it has streamed the full
   object and computed SHA-256 over it. See ontology.py's `Video.video_hash`
   docstring for the full reasoning, and DATA_FLOW.md's upload lifecycle.
   The existing `uq_video_org_hash` unique constraint is left untouched --
   standard SQL UNIQUE semantics already treat NULL as "not equal to
   anything, including another NULL," so concurrent un-hashed uploads within
   the same org never spuriously collide.
2. `error` (nullable text) added, mirroring `processing_jobs.error`'s
   existing shape -- populated only when `status == 'failed'`.

Both changes are backward compatible with any existing `videos` rows (there
are none yet in any real environment -- Video has had no real writer until
this phase).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("videos", "video_hash", existing_type=sa.String(length=64), nullable=True)
    op.add_column("videos", sa.Column("error", sa.Text(), nullable=True))


def downgrade() -> None:
    # Narrowing video_hash back to NOT NULL would fail against any row
    # ingested under Phase 4 that hasn't finished hashing yet -- documented
    # as an accepted downgrade limitation, same posture as 0001/0002's
    # offline-only-verified downgrade direction (see TECH_DEBT.md).
    op.drop_column("videos", "error")
    op.alter_column("videos", "video_hash", existing_type=sa.String(length=64), nullable=False)
