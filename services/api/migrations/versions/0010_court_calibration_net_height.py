"""court_calibrations: add net_height_m, court_width_m, court_length_m

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-01

Closes a real field-compatibility gap against `CameraCalibrationAnnotation`
(volley_domain.annotation), which has always required `net_height_m` and
defaulted `court_width_m`/`court_length_m` (9.0/18.0) -- `court_calibrations`
had none of the three until now, ahead of a real manual-calibration producer
needing to persist them (see CourtCalibration's own docstring in
ontology.py). `net_height_m` stays nullable: a homography is valid without
it, and a missing value must never silently become a fabricated default.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("court_calibrations", sa.Column("net_height_m", sa.Float(), nullable=True))
    op.add_column(
        "court_calibrations",
        sa.Column("court_width_m", sa.Float(), nullable=False, server_default="9.0"),
    )
    op.add_column(
        "court_calibrations",
        sa.Column("court_length_m", sa.Float(), nullable=False, server_default="18.0"),
    )
    op.alter_column("court_calibrations", "court_width_m", server_default=None)
    op.alter_column("court_calibrations", "court_length_m", server_default=None)


def downgrade() -> None:
    op.drop_column("court_calibrations", "court_length_m")
    op.drop_column("court_calibrations", "court_width_m")
    op.drop_column("court_calibrations", "net_height_m")
