from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.attendance.domain.repositories.attendance_session_repository import (
    AttendanceSessionRepository,
)
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException
from shared.pagination import Page, PaginationParams


@dataclass
class ListTenantAttendanceSessionsInput:
    tenant_id: UUID
    user_id: UUID
    user_role: UserRole | None = None
    pagination: PaginationParams = field(default_factory=PaginationParams)
    subject_class_id: UUID | None = None
    status: SessionStatus | None = None
    exclude_status: SessionStatus | None = None
    opened_after: datetime | None = None
    opened_before: datetime | None = None
    search: str | None = None
    sort: str = "recent"


class ListTenantAttendanceSessionsUseCase:
    def __init__(
        self,
        session_repo: AttendanceSessionRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.session_repo = session_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: ListTenantAttendanceSessionsInput) -> Page[AttendanceSession]:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        if data.user_role not in (UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR):
            raise ForbiddenException(
                "Apenas administradores, coordenadores e professores podem consultar chamadas."
            )

        professor_user_id = data.user_id if data.user_role == UserRole.PROFESSOR else None

        return await self.session_repo.list_by_tenant_paginated(
            tenant_id=data.tenant_id,
            pagination=data.pagination,
            professor_user_id=professor_user_id,
            subject_class_id=data.subject_class_id,
            status=data.status,
            exclude_status=data.exclude_status,
            opened_after=data.opened_after,
            opened_before=data.opened_before,
            search=data.search,
            sort=data.sort,
        )
