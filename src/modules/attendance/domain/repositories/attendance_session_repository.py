from typing import Protocol
from uuid import UUID

from modules.attendance.domain.entities.attendance_session import AttendanceSession


class AttendanceSessionRepository(Protocol):

    async def save(self, session: AttendanceSession) -> AttendanceSession: ...

    async def find_by_id(self, session_id: UUID) -> AttendanceSession | None: ...

    async def find_by_id_and_class(
        self, session_id: UUID, subject_class_id: UUID
    ) -> AttendanceSession | None: ...

    async def find_open_session_by_class(
        self, subject_class_id: UUID
    ) -> AttendanceSession | None: ...

    async def list_by_class(
        self, subject_class_id: UUID
    ) -> list[AttendanceSession]: ...
