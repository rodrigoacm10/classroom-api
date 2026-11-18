"""drop legacy users.fcm_token

Revision ID: c4f0a12b9d55
Revises: e7c4a92f6b31
Create Date: 2026-11-18 08:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c4f0a12b9d55"
down_revision: Union[str, Sequence[str], None] = "e7c4a92f6b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """O push usa a tabela user_fcm_tokens. A coluna users.fcm_token não é mais lida."""
    op.drop_column("users", "fcm_token")


def downgrade() -> None:
    op.add_column("users", sa.Column("fcm_token", sa.String(length=512), nullable=True))
