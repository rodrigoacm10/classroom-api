"""add cancelled value to session_status enum

Revision ID: b8d3e1f0a624
Revises: 2b8cf538cb7d
Create Date: 2026-09-13 18:32:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b8d3e1f0a624"
down_revision: Union[str, Sequence[str], None] = "2b8cf538cb7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'cancelled'")


def downgrade() -> None:
    """PostgreSQL does not support dropping a single enum value without rewriting the type."""
    pass
