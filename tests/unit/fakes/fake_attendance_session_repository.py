from uuid import UUID

from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.attendance.domain.repositories.attendance_session_repository import AttendanceSessionRepository
from shared.enums.session_status import SessionStatus


class FakeAttendanceSessionRepository(AttendanceSessionRepository):

    def __init__(self) -> None:
        self.sessions: dict[UUID, AttendanceSession] = {}

    async def save(self, session: AttendanceSession) -> AttendanceSession:
        self.sessions[session.id] = session
        return session

    async def find_by_id(self, session_id: UUID) -> AttendanceSession | None:
        return self.sessions.get(session_id)

    async def find_by_id_and_class(
        self, session_id: UUID, subject_class_id: UUID
    ) -> AttendanceSession | None:
        s = self.sessions.get(session_id)
        if s and s.subject_class_id == subject_class_id:
            return s
        return None

    async def find_open_session_by_class(
        self, subject_class_id: UUID
    ) -> AttendanceSession | None:
        for s in self.sessions.values():
            if s.subject_class_id == subject_class_id and s.status == SessionStatus.OPEN:
                return s
        return None

    async def list_by_class(
        self, subject_class_id: UUID
    ) -> list[AttendanceSession]:
        return [s for s in self.sessions.values() if s.subject_class_id == subject_class_id]

    async def close_expired_sessions(self) -> list[AttendanceSession]:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        closed: list[AttendanceSession] = []
        for session in self.sessions.values():
            if session.status == SessionStatus.OPEN and session.expires_at <= now:
                session.close()
                closed.append(session)
        return closed

