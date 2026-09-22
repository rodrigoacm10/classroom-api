from uuid import UUID

from modules.tenant.domain.entities.tenant import Tenant
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException


class DeactivateTenantUseCase:

    def __init__(self, tenant_repo: TenantRepository) -> None:
        self.tenant_repo = tenant_repo

    async def execute(self, tenant_id: UUID) -> Tenant:
        tenant = await self.tenant_repo.find_by_id(tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        tenant.active = False
        return await self.tenant_repo.save(tenant)
