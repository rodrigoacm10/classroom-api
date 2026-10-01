"""optimize_dashboard_indexes

Revision ID: 0403c82a3af5
Revises: a89b6124eefe
Create Date: 2026-10-01 10:43:19.671045

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0403c82a3af5"
down_revision: Union[str, Sequence[str], None] = "a89b6124eefe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: remove redundant/unused indexes and add targeted dashboard indexes."""
    # 1. Remover índices redundantes/não utilizados em attendance_records
    op.drop_index(
        "ix_attendance_records_session_id", table_name="attendance_records", if_exists=True
    )
    op.execute("DROP INDEX IF EXISTS idx_attendance_records_student_location;")

    # 2. Criar índices para otimização de turmas (subject_classes)
    op.create_index(
        "ix_subject_classes_tenant_lookup",
        "subject_classes",
        ["tenant_id", "deleted", "active"],
        unique=False,
    )
    op.create_index(
        "ix_subject_classes_professor_id",
        "subject_classes",
        ["professor_id"],
        unique=False,
        postgresql_where=sa.text("deleted IS FALSE"),
    )

    # 3. Criar índices em attendance_sessions
    # 3.1. Índice parcial de sessões abertas (ao vivo)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_attendance_sessions_open_active
        ON attendance_sessions (subject_class_id, opened_at DESC)
        WHERE status = 'open';
        """
    )
    # 3.2. Índice para cálculo de frequência por turma e data (últimos 30 dias / semana)
    op.create_index(
        "ix_attendance_sessions_class_opened",
        "attendance_sessions",
        ["subject_class_id", "opened_at"],
        unique=False,
        postgresql_where=sa.text("status != 'cancelled'"),
    )

    # 4. Criar índice reverso para matrículas ativas por aluno (subject_class_enrollments)
    op.create_index(
        "ix_enrollments_member_active",
        "subject_class_enrollments",
        ["tenant_member_id", "status"],
        unique=False,
        postgresql_where=sa.text("deleted IS FALSE"),
    )


def downgrade() -> None:
    """Downgrade schema: revert new indexes and restore dropped indexes."""
    # 1. Reverter novos índices
    op.drop_index(
        "ix_enrollments_member_active", table_name="subject_class_enrollments", if_exists=True
    )
    op.drop_index(
        "ix_attendance_sessions_class_opened", table_name="attendance_sessions", if_exists=True
    )
    op.drop_index(
        "ix_attendance_sessions_open_active", table_name="attendance_sessions", if_exists=True
    )
    op.drop_index("ix_subject_classes_professor_id", table_name="subject_classes", if_exists=True)
    op.drop_index("ix_subject_classes_tenant_lookup", table_name="subject_classes", if_exists=True)

    # 2. Restaurar índices removidos de attendance_records
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_attendance_records_student_location ON attendance_records USING gist (student_location);"
    )
    op.create_index(
        "ix_attendance_records_session_id", "attendance_records", ["session_id"], unique=False
    )
