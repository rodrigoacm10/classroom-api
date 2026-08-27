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
class UpdateTenantMemberRoleInput:
    tenant_id: UUID
    user_id_to_update: UUID
    new_role: UserRole


class UpdateTenantMemberRoleUseCase:

    def __init__(
        self,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: UpdateTenantMemberRoleInput) -> TenantMember:
        # 1. Verificar se a tenant existe e não está deletada
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        # 2. Buscar o membro ativo a ter sua role alterada
        member = await self.member_repo.find_by_tenant_and_user(
            tenant_id=data.tenant_id,
            user_id=data.user_id_to_update,
            include_deleted=False,
        )
        if not member:
            raise ResourceNotFoundException("Membro não encontrado nesta instituição.")

        # 3. Se a role não está mudando, nada a fazer
        if member.role == data.new_role:
            return member

        # 4. Trava de segurança: se o membro é atualmente ADMIN e está sendo alterado para outra role,
        # verificar se não estamos rebaixando o único administrador da instituição.
        if member.role == UserRole.ADMIN and data.new_role != UserRole.ADMIN:
            active_admins = await self.member_repo.count_active_admins(data.tenant_id)
            if active_admins <= 1:
                raise BusinessRuleException(
                    "Não é possível alterar a função do único administrador da instituição."
                )

        # 5. Atualiza a role e persiste
        member.role = data.new_role
        return await self.member_repo.save(member)
