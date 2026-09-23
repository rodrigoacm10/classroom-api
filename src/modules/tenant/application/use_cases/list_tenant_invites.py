from dataclasses import dataclass, field
from uuid import UUID

from modules.tenant.domain.entities.tenant_invite import TenantInvite
from modules.tenant.domain.repositories.tenant_invite_repository import TenantInviteRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.enums.user_role import UserRole
from shared.exceptions import ResourceNotFoundException
from shared.pagination import Page, PaginationParams


@dataclass
class ListTenantInvitesInput:
    tenant_id: UUID
    pagination: PaginationParams = field(default_factory=PaginationParams)
    status: str | None = None
    role: UserRole | None = None
    search: str | None = None


class ListTenantInvitesUseCase:

    def __init__(
        self,
        tenant_repo: TenantRepository,
        invite_repo: TenantInviteRepository,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.invite_repo = invite_repo

    async def execute(self, data: ListTenantInvitesInput) -> Page[TenantInvite]:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Tenant não encontrada.")

        return await self.invite_repo.find_by_tenant_id_paginated(
            tenant_id=data.tenant_id,
            pagination=data.pagination,
            status=data.status,
            role=data.role,
            search=data.search,
        )
