from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from modules.attendance.domain.entities.student_attendance_history_item import (
    StudentAttendanceHistoryItem,
)
from modules.attendance.domain.repositories.attendance_session_repository import (
    AttendanceSessionRepository,
)
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException
from shared.pagination import Page, PaginationParams


@dataclass
class ListStudentAttendanceHistoryInput:
    tenant_id: UUID
    user_id: UUID
    pagination: PaginationParams
    user_role: UserRole | None = None
    target_tenant_member_id: UUID | None = None
    subject_class_id: UUID | None = None
    status: SessionStatus | None = None
    opened_after: datetime | None = None
    opened_before: datetime | None = None


class ListStudentAttendanceHistoryUseCase:
    def __init__(
        self,
        session_repo: AttendanceSessionRepository,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.session_repo = session_repo
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(
        self, data: ListStudentAttendanceHistoryInput
    ) -> Page[StudentAttendanceHistoryItem]:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        caller_member = await self.member_repo.find_by_tenant_and_user(data.tenant_id, data.user_id)
        if not caller_member or getattr(caller_member, "deleted", False):
            raise ForbiddenException("Usuário não é membro desta instituição.")

        if data.target_tenant_member_id is not None:
            if caller_member.role not in (UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR):
                raise ForbiddenException(
                    "Apenas administradores e professores podem consultar histórico de terceiros."
                )

            target_student = await self.member_repo.find_by_id(data.target_tenant_member_id)
            if not target_student or getattr(target_student, "deleted", False):
                raise ResourceNotFoundException("Aluno não encontrado.")
            if target_student.tenant_id != data.tenant_id or target_student.role != UserRole.ALUNO:
                raise ResourceNotFoundException("Aluno não encontrado nesta instituição.")

            student_member_id = target_student.id
        else:
            if caller_member.role != UserRole.ALUNO:
                raise ForbiddenException("Apenas alunos podem consultar seu histórico de chamadas.")
            student_member_id = caller_member.id

        return await self.session_repo.list_history_by_student_paginated(
            tenant_id=data.tenant_id,
            tenant_member_id=student_member_id,
            pagination=data.pagination,
            subject_class_id=data.subject_class_id,
            status=data.status,
            opened_after=data.opened_after,
            opened_before=data.opened_before,
        )
