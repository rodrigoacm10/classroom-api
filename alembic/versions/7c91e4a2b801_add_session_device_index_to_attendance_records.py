"""add_session_device_index_to_attendance_records

Revision ID: 7c91e4a2b801
Revises: 420cdc3d07d3
Create Date: 2026-11-03 15:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c91e4a2b801"
down_revision: Union[str, Sequence[str], None] = "420cdc3d07d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add partial composite index (session_id, device_id) on attendance_records."""
    op.create_index(
        "ix_attendance_records_session_device",
        "attendance_records",
        ["session_id", "device_id"],
        unique=False,
        postgresql_where=sa.text("device_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema: drop ix_attendance_records_session_device index."""
    op.drop_index(
        "ix_attendance_records_session_device",
        table_name="attendance_records",
        if_exists=True,
    )

