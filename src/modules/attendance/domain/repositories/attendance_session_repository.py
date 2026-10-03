from datetime import datetime
from typing import Protocol
from uuid import UUID

from modules.attendance.domain.entities.attendance_session import AttendanceSession
from shared.enums.session_status import SessionStatus
from shared.pagination import Page, PaginationParams


class AttendanceSessionRepository(Protocol):
    async def save(self, session: AttendanceSession) -> AttendanceSession: ...

    async def find_by_id(self, session_id: UUID) -> AttendanceSession | None: ...

    async def find_by_id_and_class(
        self, session_id: UUID, subject_class_id: UUID
    ) -> AttendanceSession | None: ...

    async def find_open_session_by_class(
        self, subject_class_id: UUID
    ) -> AttendanceSession | None: ...

    async def list_by_class(self, subject_class_id: UUID) -> list[AttendanceSession]: ...

    async def find_by_class_paginated(
        self,
        subject_class_id: UUID,
        pagination: PaginationParams,
        status: SessionStatus | None = None,
        opened_after: datetime | None = None,
        opened_before: datetime | None = None,
    ) -> Page[AttendanceSession]: ...

    async def close_expired_sessions(self) -> list[AttendanceSession]: ...

    async def list_active_sessions_by_tenant(
        self,
        tenant_id: UUID,
        professor_user_id: UUID | None = None,
    ) -> list[AttendanceSession]: ...

    async def list_by_tenant_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        professor_user_id: UUID | None = None,
        subject_class_id: UUID | None = None,
        status: SessionStatus | None = None,
        exclude_status: SessionStatus | None = None,
        opened_after: datetime | None = None,
        opened_before: datetime | None = None,
        search: str | None = None,
    ) -> Page[AttendanceSession]: ...

    async def get_metrics_by_tenant(
        self,
        tenant_id: UUID,
        professor_user_id: UUID | None = None,
        days: int = 30,
    ) -> dict: ...
