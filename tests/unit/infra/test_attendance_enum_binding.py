from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from infra.database.models.attendance_record import AttendanceRecordModel
from infra.database.models.attendance_session import AttendanceSessionModel
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus


def _bound_values(stmt) -> list[object]:
    compiled = stmt.compile(dialect=postgresql.dialect())
    return list(compiled.params.values())


class TestAttendanceEnumBinding:
    def test_session_status_column_uses_enum_values_not_names(self):
        """O tipo nativo session_status no Postgres foi criado com 'open'/'closed'/'cancelled'."""
        assert list(AttendanceSessionModel.status.type.enums) == [
            "open",
            "closed",
            "cancelled",
        ]

    def test_find_open_session_filter_binds_lowercase_value(self):
        """
        find_open_session_by_class compara status com SessionStatus.OPEN.
        Sem values_callable o SQLAlchemy envia o nome 'OPEN' e o Postgres rejeita.
        """
        stmt = select(AttendanceSessionModel.id).where(
            AttendanceSessionModel.status == SessionStatus.OPEN,
        )
        bound = _bound_values(stmt)

        assert SessionStatus.OPEN.value in bound
        assert SessionStatus.OPEN.name not in bound

    def test_cancelled_and_closed_filters_bind_lowercase_values(self):
        for status in (SessionStatus.CLOSED, SessionStatus.CANCELLED):
            stmt = select(AttendanceSessionModel.id).where(
                AttendanceSessionModel.status == status,
            )
            bound = _bound_values(stmt)

            assert status.value in bound
            assert status.name not in bound

    def test_record_status_column_uses_enum_values_not_names(self):
        assert list(AttendanceRecordModel.record_status.type.enums) == [
            "regular",
            "irregular",
            "approved",
            "rejected",
        ]

    def test_record_status_filter_binds_lowercase_value(self):
        stmt = select(AttendanceRecordModel.id).where(
            AttendanceRecordModel.record_status == RecordStatus.REGULAR,
        )
        bound = _bound_values(stmt)

        assert RecordStatus.REGULAR.value in bound
        assert RecordStatus.REGULAR.name not in bound
