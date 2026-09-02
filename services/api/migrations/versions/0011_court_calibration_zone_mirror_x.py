"""court_calibrations: add zone_mirror_x

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-01

Resolves ml/court/rotation.py's `mirror_x` parameter with a real human
confirmation instead of a guess -- that module's own docstring says it
"must be verified per camera setup against a frame with a known server
position, never guessed." Nullable: a calibration is fully valid for side
(near/far) and front/back-row without it; only the exact numbered zone
(1-6) needs it, and stays unavailable rather than guessed until set.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("court_calibrations", sa.Column("zone_mirror_x", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("court_calibrations", "zone_mirror_x")
