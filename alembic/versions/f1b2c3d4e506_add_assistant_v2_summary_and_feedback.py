"""add assistant v2 summary and feedback columns

Revision ID: f1b2c3d4e506
Revises: d9a3e5b7c102
Create Date: 2026-11-22 16:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1b2c3d4e506"
down_revision: Union[str, Sequence[str], None] = "d9a3e5b7c102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add conversation summary columns and message feedback columns."""
    op.add_column("chat_conversations", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "chat_conversations",
        sa.Column(
            "summary_message_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )

    op.add_column(
        "chat_messages",
        sa.Column("feedback_rating", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "chat_messages",
        sa.Column("feedback_comment", sa.Text(), nullable=True),
    )
    op.add_column(
        "chat_messages",
        sa.Column("feedback_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Drop message feedback columns and conversation summary columns."""
    op.drop_column("chat_messages", "feedback_updated_at")
    op.drop_column("chat_messages", "feedback_comment")
    op.drop_column("chat_messages", "feedback_rating")

    op.drop_column("chat_conversations", "summary_message_count")
    op.drop_column("chat_conversations", "summary")

