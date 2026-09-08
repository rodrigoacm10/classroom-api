"""create attendance tables

Revision ID: a8f7e2d19012
Revises: 06e811fc8b7a
Create Date: 2026-08-31 14:37:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2


# revision identifiers, used by Alembic.
revision: str = 'a8f7e2d19012'
down_revision: Union[str, Sequence[str], None] = '06e811fc8b7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    session_status_enum = sa.Enum('open', 'closed', name='session_status')
    session_status_enum.create(op.get_bind(), checkfirst=True)

    record_status_enum = sa.Enum('regular', 'irregular', 'approved', 'rejected', name='record_status')
    record_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'attendance_sessions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('subject_class_id', sa.UUID(), nullable=False),
        sa.Column('room_id', sa.UUID(), nullable=True),
        sa.Column('day_code', sa.String(length=10), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', session_status_enum, nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['subject_class_id'], ['subject_classes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_attendance_sessions_subject_class_id', 'attendance_sessions', ['subject_class_id'], unique=False)

    op.create_table(
        'attendance_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('tenant_member_id', sa.UUID(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('student_location', geoalchemy2.types.Geography(geometry_type='POINT', srid=4326, dimension=2, from_text='ST_GeogFromText', name='geography', nullable=False), nullable=False),
        sa.Column('distance_meters', sa.Float(), nullable=False),
        sa.Column('within_radius', sa.Boolean(), nullable=False),
        sa.Column('gps_accuracy_meters', sa.Float(), nullable=True),
        sa.Column('record_status', record_status_enum, nullable=False, server_default='regular'),
        sa.Column('irregularity_flags', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False),
        sa.Column('reviewed_by', sa.UUID(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('device_id', sa.String(length=64), nullable=True),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('device_info', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('evidence_photo_url', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['reviewed_by'], ['tenant_members.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_id'], ['attendance_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_member_id'], ['tenant_members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'tenant_member_id', name='uq_attendance_record_session_member')
    )
    op.create_index('ix_attendance_records_session_id', 'attendance_records', ['session_id'], unique=False)
    op.create_index('ix_attendance_records_tenant_member_id', 'attendance_records', ['tenant_member_id'], unique=False)
    op.execute("CREATE INDEX IF NOT EXISTS idx_attendance_records_student_location ON attendance_records USING gist (student_location);")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_attendance_records_student_location', table_name='attendance_records', postgresql_using='gist')
    op.drop_index('ix_attendance_records_tenant_member_id', table_name='attendance_records')
    op.drop_index('ix_attendance_records_session_id', table_name='attendance_records')
    op.drop_table('attendance_records')

    op.drop_index('ix_attendance_sessions_subject_class_id', table_name='attendance_sessions')
    op.drop_table('attendance_sessions')

    record_status_enum = sa.Enum('regular', 'irregular', 'approved', 'rejected', name='record_status')
    record_status_enum.drop(op.get_bind(), checkfirst=True)

    session_status_enum = sa.Enum('open', 'closed', name='session_status')
    session_status_enum.drop(op.get_bind(), checkfirst=True)
