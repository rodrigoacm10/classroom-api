from dataclasses import dataclass
from uuid import UUID

from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.user_role import UserRole
from shared.exceptions import (
    BusinessRuleException,
    ResourceAlreadyExistsException,
    ResourceNotFoundException,
)


@dataclass
class EnrollStudentInput:
    subject_class_id: UUID
    tenant_member_id: UUID
    tenant_id: UUID


class EnrollStudentUseCase:

    def __init__(
        self,
        enrollment_repo: EnrollmentRepository,
        subject_class_repo: SubjectClassRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.enrollment_repo = enrollment_repo
        self.subject_class_repo = subject_class_repo
        self.member_repo = member_repo

    async def execute(self, data: EnrollStudentInput) -> Enrollment:
        # 1. Verifica se a turma existe e não foi deletada
        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            subject_class_id=data.subject_class_id,
            tenant_id=data.tenant_id,
        )
        if not subject_class:
            raise ResourceNotFoundException("Turma não encontrada.")

        # 2. Busca o TenantMember
        member = await self.member_repo.find_by_id(data.tenant_member_id, include_deleted=False)
        if not member:
            raise ResourceNotFoundException("Membro não encontrado.")

        # 3. Valida que o membro pertence ao mesmo tenant da turma
        if member.tenant_id != data.tenant_id:
            raise BusinessRuleException("O membro não pertence a esta instituição.")

        # 4. Valida que o membro tem papel ALUNO
        if member.role != UserRole.ALUNO:
            raise BusinessRuleException(
                "Apenas alunos podem ser matriculados em turmas. "
                f"O membro possui papel '{member.role.value}'."
            )

        # 5. Verifica se já existe matrícula (não deletada)
        existing = await self.enrollment_repo.find_by_class_and_member(
            subject_class_id=data.subject_class_id,
            tenant_member_id=data.tenant_member_id,
            include_deleted=False,
        )
        if existing:
            if existing.status == EnrollmentStatus.ACTIVE:
                raise ResourceAlreadyExistsException("O aluno já está matriculado nesta turma.")
            # Se dropped, reativa a matrícula
            existing.status = EnrollmentStatus.ACTIVE
            return await self.enrollment_repo.save(existing)

        # 6. Cria nova matrícula
        enrollment = Enrollment(
            subject_class_id=data.subject_class_id,
            tenant_member_id=data.tenant_member_id,
        )
        return await self.enrollment_repo.save(enrollment)
