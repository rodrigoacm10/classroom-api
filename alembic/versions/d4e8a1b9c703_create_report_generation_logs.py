"""create report_generation_logs table

Revision ID: d4e8a1b9c703
Revises: b8d3e1f0a624
Create Date: 2026-09-10 17:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e8a1b9c703"
down_revision: Union[str, Sequence[str], None] = "b8d3e1f0a624"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "report_generation_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("subject_class_id", sa.UUID(), nullable=False),
        sa.Column("strategy", sa.String(length=30), nullable=False),
        sa.Column("workers_used", sa.Integer(), nullable=False),
        sa.Column("items_processed", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["subject_class_id"], ["subject_classes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("report_generation_logs")
