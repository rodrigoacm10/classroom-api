from dataclasses import dataclass
from uuid import UUID

from modules.tenant.domain.entities.members_metrics import MembersMetrics
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from shared.exceptions import ResourceNotFoundException


@dataclass
class GetMembersMetricsInput:
    tenant_id: UUID


class GetMembersMetricsUseCase:
    """Consolida os indicadores de membros da instituição (professores, coordenadores, admins e turmas)."""

    def __init__(
        self,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: GetMembersMetricsInput) -> MembersMetrics:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Tenant não encontrada.")

        return await self.member_repo.get_members_metrics(tenant_id=data.tenant_id)

