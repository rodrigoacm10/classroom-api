from dataclasses import dataclass
from uuid import UUID

from modules.attendance.domain.entities.student_active_session import StudentActiveSession
from modules.attendance.domain.repositories.attendance_session_repository import (
    AttendanceSessionRepository,
)
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException


@dataclass
class ListStudentActiveSessionsInput:
    tenant_id: UUID
    user_id: UUID
    user_role: UserRole | None = None


class ListStudentActiveSessionsUseCase:
    def __init__(
        self,
        session_repo: AttendanceSessionRepository,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.session_repo = session_repo
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: ListStudentActiveSessionsInput) -> list[StudentActiveSession]:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        member = await self.member_repo.find_by_tenant_and_user(data.tenant_id, data.user_id)
        if not member or getattr(member, "deleted", False):
            raise ForbiddenException("Usuário não é membro desta instituição.")

        if member.role != UserRole.ALUNO:
            raise ForbiddenException("Apenas alunos podem consultar suas chamadas ativas.")

        return await self.session_repo.list_active_sessions_by_student(
            tenant_id=data.tenant_id,
            tenant_member_id=member.id,
        )
