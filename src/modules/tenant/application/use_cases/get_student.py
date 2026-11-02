from dataclasses import dataclass
from uuid import UUID

from modules.tenant.domain.entities.tenant_member import TenantMember
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from shared.exceptions import ResourceNotFoundException


@dataclass
class GetStudentInput:
    tenant_id: UUID
    student_id: UUID
    professor_user_id: UUID | None = None
    include_deleted: bool = False


class GetStudentUseCase:
    def __init__(
        self,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: GetStudentInput) -> TenantMember:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição não encontrada.")

        student = await self.member_repo.find_student_with_metrics_by_id(
            tenant_id=data.tenant_id,
            student_id=data.student_id,
            professor_user_id=data.professor_user_id,
            include_deleted=data.include_deleted,
        )
        if not student:
            raise ResourceNotFoundException("Aluno não encontrado nesta instituição.")

        return student
