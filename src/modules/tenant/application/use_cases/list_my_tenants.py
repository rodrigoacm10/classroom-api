from dataclasses import dataclass
from uuid import UUID

from modules.tenant.domain.entities.tenant import Tenant
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from shared.enums.user_role import UserRole


@dataclass
class MyTenantItem:
    tenant: Tenant
    role: UserRole


class ListMyTenantsUseCase:

    def __init__(
        self,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, user_id: UUID) -> list[MyTenantItem]:
        memberships = await self.member_repo.find_by_user_id(user_id)
        result: list[MyTenantItem] = []

        for m in memberships:
            tenant = await self.tenant_repo.find_by_id(m.tenant_id)
            if tenant:
                result.append(MyTenantItem(tenant=tenant, role=m.role))

        return result
