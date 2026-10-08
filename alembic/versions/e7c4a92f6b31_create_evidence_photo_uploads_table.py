"""create evidence_photo_uploads table

Revision ID: e7c4a92f6b31
Revises: 0403c82a3af5
Create Date: 2026-10-07 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7c4a92f6b31'
down_revision: Union[str, Sequence[str], None] = '0403c82a3af5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'evidence_photo_uploads',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('file_key', sa.String(length=512), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('pending', 'confirmed', 'expired', name='upload_status'),
            server_default='pending',
            nullable=False,
        ),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('attendance_record_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['attendance_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['attendance_record_id'], ['attendance_records.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_evidence_photo_uploads_status', 'evidence_photo_uploads', ['status'])
    op.create_index('ix_evidence_photo_uploads_session_id', 'evidence_photo_uploads', ['session_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_evidence_photo_uploads_session_id', table_name='evidence_photo_uploads')
    op.drop_index('ix_evidence_photo_uploads_status', table_name='evidence_photo_uploads')
    op.drop_table('evidence_photo_uploads')
    sa.Enum(name='upload_status').drop(op.get_bind(), checkfirst=True)