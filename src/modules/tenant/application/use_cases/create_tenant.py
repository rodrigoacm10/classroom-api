from dataclasses import dataclass

from modules.tenant.domain.entities.tenant import Tenant
from modules.tenant.domain.entities.tenant_member import TenantMember
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from shared.enums.user_role import UserRole
from shared.exceptions import ResourceAlreadyExistsException


@dataclass
class CreateTenantInput:
    name: str
    slug: str
    owner_user_id: str


@dataclass
class CreateTenantOutput:
    tenant: Tenant
    member: TenantMember


class CreateTenantUseCase:

    def __init__(
        self,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: CreateTenantInput) -> CreateTenantOutput:
        existing = await self.tenant_repo.find_by_slug(data.slug)
        if existing:
            raise ResourceAlreadyExistsException("Uma instituição/tenant com este slug já existe.")

        tenant = Tenant(name=data.name, slug=data.slug)
        saved_tenant = await self.tenant_repo.save(tenant)

        # O criador da tenant torna-se automaticamente ADMIN da mesma
        from uuid import UUID
        owner_uuid = UUID(data.owner_user_id) if isinstance(data.owner_user_id, str) else data.owner_user_id

        owner_member = TenantMember(
            tenant_id=saved_tenant.id,
            user_id=owner_uuid,
            role=UserRole.ADMIN,
        )
        saved_member = await self.member_repo.save(owner_member)

        return CreateTenantOutput(tenant=saved_tenant, member=saved_member)
