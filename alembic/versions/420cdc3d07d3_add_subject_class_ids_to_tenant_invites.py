"""add_subject_class_ids_to_tenant_invites

Revision ID: 420cdc3d07d3
Revises: 0403c82a3af5
Create Date: 2026-10-30 18:55:01.648902

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '420cdc3d07d3'
down_revision: Union[str, Sequence[str], None] = '0403c82a3af5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add subject_class_ids JSON column to tenant_invites."""
    op.add_column(
        "tenant_invites",
        sa.Column("subject_class_ids", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema: drop subject_class_ids column from tenant_invites."""
    op.drop_column("tenant_invites", "subject_class_ids")
