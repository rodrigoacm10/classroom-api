"""create_user_fcm_tokens_table

Revision ID: 2b8cf538cb7d
Revises: a8f7e2d19012
Create Date: 2026-08-31 20:30:51.897311

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2b8cf538cb7d'
down_revision: Union[str, Sequence[str], None] = 'a8f7e2d19012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_fcm_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('device_id', sa.String(length=64), nullable=False),
        sa.Column('fcm_token', sa.Text(), nullable=False),
        sa.Column('platform', sa.String(length=20), nullable=False),
        sa.Column('app_version', sa.String(length=20), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_user_fcm_tokens_user_device', 'user_fcm_tokens', ['user_id', 'device_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_user_fcm_tokens_user_device', table_name='user_fcm_tokens')
    op.drop_table('user_fcm_tokens')
