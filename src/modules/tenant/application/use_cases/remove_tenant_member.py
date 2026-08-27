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
class RemoveTenantMemberInput:
    tenant_id: UUID
    user_id_to_remove: UUID


class RemoveTenantMemberUseCase:

    def __init__(
        self,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: RemoveTenantMemberInput) -> TenantMember:
        # 1. Verificar se a tenant existe e não está deletada
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        # 2. Buscar o membro ativo a ser removido
        member = await self.member_repo.find_by_tenant_and_user(
            tenant_id=data.tenant_id,
            user_id=data.user_id_to_remove,
            include_deleted=False,
        )
        if not member:
            raise ResourceNotFoundException("Membro não encontrado nesta instituição.")

        # 3. Trava de segurança: Não permitir remover o único ADMIN da instituição
        if member.role == UserRole.ADMIN:
            active_admins = await self.member_repo.count_active_admins(data.tenant_id)
            if active_admins <= 1:
                raise BusinessRuleException("Não é possível remover o único administrador da instituição.")

        # 4. Soft Delete
        member.deleted = True
        return await self.member_repo.save(member)
