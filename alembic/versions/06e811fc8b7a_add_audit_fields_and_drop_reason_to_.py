"""add audit fields and drop_reason to subject_class_enrollments

Revision ID: 06e811fc8b7a
Revises: c64f27978b95
Create Date: 2026-08-31 10:04:29.026876

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06e811fc8b7a'
down_revision: Union[str, Sequence[str], None] = 'c64f27978b95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    drop_reason_enum = sa.Enum('admin_cancellation', 'role_change', name='drop_reason')
    drop_reason_enum.create(op.get_bind(), checkfirst=True)

    op.add_column('subject_class_enrollments', sa.Column('dropped_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('subject_class_enrollments', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('subject_class_enrollments', sa.Column('drop_reason', drop_reason_enum, nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    drop_reason_enum = sa.Enum('admin_cancellation', 'role_change', name='drop_reason')
    op.drop_column('subject_class_enrollments', 'drop_reason')
    op.drop_column('subject_class_enrollments', 'deleted_at')
    op.drop_column('subject_class_enrollments', 'dropped_at')
    drop_reason_enum.drop(op.get_bind(), checkfirst=True)
