"""add_custom_location_to_attendance_sessions

Revision ID: e81a3b4c5d6e
Revises: 7c91e4a2b801
Create Date: 2026-11-03 17:30:00.000000

"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e81a3b4c5d6e"
down_revision: Union[str, Sequence[str], None] = "7c91e4a2b801"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add custom location columns to attendance_sessions."""
    op.add_column(
        "attendance_sessions",
        sa.Column(
            "custom_location",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                from_text="ST_GeogFromText",
                name="geography",
                nullable=True,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "attendance_sessions",
        sa.Column("custom_latitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "attendance_sessions",
        sa.Column("custom_longitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "attendance_sessions",
        sa.Column("custom_tolerance_radius_meters", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema: remove custom location columns from attendance_sessions."""
    op.drop_column("attendance_sessions", "custom_tolerance_radius_meters")
    op.drop_column("attendance_sessions", "custom_longitude")
    op.drop_column("attendance_sessions", "custom_latitude")
    op.drop_column("attendance_sessions", "custom_location")

