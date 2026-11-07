from dataclasses import dataclass
from uuid import UUID

from modules.tenant.domain.entities.students_metrics import StudentsMetrics
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from shared.exceptions import ResourceNotFoundException


@dataclass
class GetStudentsMetricsInput:
    tenant_id: UUID
    professor_user_id: UUID | None = None


class GetStudentsMetricsUseCase:
    """Consolida os indicadores de alunos no tenant ativo (ou escopo do professor)."""

    def __init__(
        self,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: GetStudentsMetricsInput) -> StudentsMetrics:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Tenant não encontrada.")

        return await self.member_repo.get_students_metrics(
            tenant_id=data.tenant_id,
            professor_user_id=data.professor_user_id,
        )
