from dataclasses import dataclass
from uuid import UUID

from modules.tenant.domain.entities.tenant_invite import TenantInvitesMetrics
from modules.tenant.domain.repositories.tenant_invite_repository import TenantInviteRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class GetTenantInvitesMetricsInput:
    tenant_id: UUID
    days: int = 30


class GetTenantInvitesMetricsUseCase:
    def __init__(
        self,
        tenant_repo: TenantRepository,
        invite_repo: TenantInviteRepository,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.invite_repo = invite_repo

    async def execute(self, data: GetTenantInvitesMetricsInput) -> TenantInvitesMetrics:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        return await self.invite_repo.get_metrics(
            tenant_id=data.tenant_id,
            days=data.days,
        )
