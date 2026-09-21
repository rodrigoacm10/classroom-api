from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.attendance.domain.entities.attendance_session import AttendanceSession
from shared.enums.session_status import SessionStatus


class TestAttendanceSessionDuration:
    def test_duration_minutes_from_opened_and_expires(self):
        opened = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
        session = AttendanceSession(
            subject_class_id=uuid4(),
            day_code="ABC123",
            opened_at=opened,
            expires_at=opened + timedelta(minutes=20),
            status=SessionStatus.OPEN,
        )
        assert session.duration_minutes == 20
        assert session.total_students == 0
        assert session.confirmed_count == 0
        assert session.irregular_count == 0

    def test_duration_minutes_never_negative(self):
        opened = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
        session = AttendanceSession(
            subject_class_id=uuid4(),
            day_code="ABC123",
            opened_at=opened,
            expires_at=opened - timedelta(minutes=5),
        )
        assert session.duration_minutes == 0
