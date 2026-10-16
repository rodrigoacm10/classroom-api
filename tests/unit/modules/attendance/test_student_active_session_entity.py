from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.attendance.domain.entities.student_active_session import StudentActiveSession
from shared.enums.record_status import RecordStatus


class TestStudentActiveSessionEntity:
    def test_duration_minutes_with_timezone_aware(self):
        """Calcula duração em minutos quando os datetimes possuem fuso horário."""
        now = datetime.now(timezone.utc)
        session = StudentActiveSession(
            session_id=uuid4(),
            subject_class_id=uuid4(),
            subject_class_name="Engenharia de Software",
            discipline_name="ES-01",
            opened_at=now,
            expires_at=now + timedelta(minutes=25),
            already_confirmed=False,
        )

        assert session.duration_minutes == 25
        assert session.already_confirmed is False
        assert session.room_id is None
        assert session.room_name is None
        assert session.record_id is None
        assert session.record_status is None

    def test_duration_minutes_with_naive_datetimes(self):
        """Calcula duração convertendo naive datetimes para UTC sem gerar erro."""
        opened = datetime(2026, 10, 15, 14, 0, 0)
        expires = datetime(2026, 10, 15, 14, 45, 0)
        session = StudentActiveSession(
            session_id=uuid4(),
            subject_class_id=uuid4(),
            subject_class_name="Banco de Dados",
            discipline_name="BD-02",
            opened_at=opened,
            expires_at=expires,
            already_confirmed=True,
            record_id=uuid4(),
            record_status=RecordStatus.REGULAR,
        )

        assert session.duration_minutes == 45
        assert session.already_confirmed is True
        assert session.record_status == RecordStatus.REGULAR

    def test_duration_minutes_never_negative(self):
        """Retorna 0 se expires_at for anterior ou igual a opened_at."""
        now = datetime.now(timezone.utc)
        session = StudentActiveSession(
            session_id=uuid4(),
            subject_class_id=uuid4(),
            subject_class_name="Cálculo Diferencial",
            discipline_name="MAT-101",
            opened_at=now,
            expires_at=now - timedelta(minutes=5),
            already_confirmed=False,
        )

        assert session.duration_minutes == 0
