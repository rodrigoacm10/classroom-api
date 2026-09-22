from dataclasses import dataclass
from uuid import UUID

from modules.tenant.domain.entities.tenant_member import TenantMember
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class AddTenantMemberInput:
    tenant_id: UUID
    user_id: UUID
    role: UserRole


class AddTenantMemberUseCase:

    def __init__(
        self,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: AddTenantMemberInput) -> TenantMember:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant:
            raise ResourceNotFoundException("Tenant não encontrada.")

        existing = await self.member_repo.find_by_tenant_and_user(
            tenant_id=data.tenant_id, user_id=data.user_id
        )
        if existing:
            raise BusinessRuleException("Usuário já é membro desta tenant.")

        member = TenantMember(
            tenant_id=data.tenant_id,
            user_id=data.user_id,
            role=data.role,
        )

        return await self.member_repo.save(member)
