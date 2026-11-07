"""add_active_to_subject_classes_table

Revision ID: a89b6124eefe
Revises: d4e8a1b9c703
Create Date: 2026-09-29 20:55:07.777542

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a89b6124eefe"
down_revision: Union[str, Sequence[str], None] = "d4e8a1b9c703"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "subject_classes",
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("subject_classes", "active")
