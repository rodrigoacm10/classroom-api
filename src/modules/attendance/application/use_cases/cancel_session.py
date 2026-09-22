from dataclasses import dataclass
from uuid import UUID

from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.attendance.domain.repositories.attendance_session_repository import AttendanceSessionRepository
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository, TenantRepository
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.exceptions import (
    BusinessRuleException,
    ForbiddenException,
    ResourceAlreadyExistsException,
    ResourceNotFoundException,
)


@dataclass
class CancelAttendanceSessionInput:
    tenant_id: UUID
    subject_class_id: UUID
    session_id: UUID
    user_id: UUID
    user_role: UserRole | None


class CancelAttendanceSessionUseCase:

    def __init__(
        self,
        session_repo: AttendanceSessionRepository,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.session_repo = session_repo
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: CancelAttendanceSessionInput) -> AttendanceSession:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            data.subject_class_id, data.tenant_id
        )
        if not subject_class or getattr(subject_class, "deleted", False):
            raise ResourceNotFoundException("Turma não encontrada.")

        session = await self.session_repo.find_by_id_and_class(data.session_id, data.subject_class_id)
        if not session:
            raise ResourceNotFoundException("Sessão de chamada não encontrada.")

        member = await self.member_repo.find_by_tenant_and_user(data.tenant_id, data.user_id)
        if not member:
            raise ForbiddenException("Usuário não é membro desta instituição.")

        is_admin = data.user_role == UserRole.ADMIN or member.role == UserRole.ADMIN
        is_professor = subject_class.professor_id == member.id

        if not (is_admin or is_professor):
            raise ForbiddenException("Apenas o professor da turma ou um administrador podem cancelar chamadas.")

        if session.status == SessionStatus.CANCELLED:
            raise ResourceAlreadyExistsException("A chamada já está cancelada.")

        if session.status == SessionStatus.CLOSED:
            raise BusinessRuleException("A chamada já foi encerrada e não pode ser cancelada.")

        session.cancel()
        return await self.session_repo.save(session)
