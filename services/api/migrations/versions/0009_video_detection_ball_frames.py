"""add video_detection_frames.ball_detections

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-31

Adds exploratory per-frame ball-box detections (RF-DETR's COCO "sports
ball" class, id 37) alongside the existing player detections -- see
VideoDetectionFrame's docstring in ontology.py. `server_default='[]'` backs
every pre-existing row so the column can be NOT NULL from the start rather
than a nullable column the app has to null-check forever.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "video_detection_frames",
        sa.Column("ball_detections", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.alter_column("video_detection_frames", "ball_detections", server_default=None)


def downgrade() -> None:
    op.drop_column("video_detection_frames", "ball_detections")
