from datetime import datetime
from uuid import UUID

from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.attendance.domain.repositories.attendance_session_repository import AttendanceSessionRepository
from shared.enums.session_status import SessionStatus
from shared.pagination import Page, PaginationParams, paginate_list


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

    async def find_by_class_paginated(
        self,
        subject_class_id: UUID,
        pagination: PaginationParams,
        status: SessionStatus | None = None,
        opened_after: datetime | None = None,
        opened_before: datetime | None = None,
    ) -> Page[AttendanceSession]:
        items = [s for s in self.sessions.values() if s.subject_class_id == subject_class_id]

        if status is not None:
            items = [s for s in items if s.status == status]

        if opened_after is not None:
            items = [s for s in items if s.opened_at >= opened_after]

        if opened_before is not None:
            items = [s for s in items if s.opened_at <= opened_before]

        items.sort(key=lambda s: s.opened_at, reverse=True)
        return paginate_list(items, pagination)

    async def close_expired_sessions(self) -> list[AttendanceSession]:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        closed: list[AttendanceSession] = []
        for session in self.sessions.values():
            if session.status == SessionStatus.OPEN and session.expires_at <= now:
                session.close()
                closed.append(session)
        return closed

