from dataclasses import dataclass
from uuid import UUID

from modules.attendance.domain.repositories.attendance_session_repository import (
    AttendanceSessionRepository,
)
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException


@dataclass
class GetAttendanceMetricsInput:
    tenant_id: UUID
    user_id: UUID
    user_role: UserRole | None = None
    days: int = 30


class GetAttendanceMetricsUseCase:
    def __init__(
        self,
        session_repo: AttendanceSessionRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.session_repo = session_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: GetAttendanceMetricsInput) -> dict:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        if data.user_role not in (UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR):
            raise ForbiddenException(
                "Apenas administradores, coordenadores e professores podem consultar métricas de chamada."
            )

        professor_user_id = data.user_id if data.user_role == UserRole.PROFESSOR else None

        return await self.session_repo.get_metrics_by_tenant(
            tenant_id=data.tenant_id,
            professor_user_id=professor_user_id,
            days=data.days,
        )
