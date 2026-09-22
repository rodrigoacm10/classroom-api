from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from modules.tenant.domain.entities.tenant_invite import TenantInvite
from modules.tenant.domain.repositories.tenant_invite_repository import TenantInviteRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class RevokeInviteInput:
    tenant_id: UUID
    invite_id: UUID


class RevokeInviteUseCase:

    def __init__(
        self,
        tenant_repo: TenantRepository,
        invite_repo: TenantInviteRepository,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.invite_repo = invite_repo

    async def execute(self, data: RevokeInviteInput) -> TenantInvite:
        # 1. Verifica se a tenant existe e não está deletada
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        # 2. Busca o convite pelo ID
        invite = await self.invite_repo.find_by_id(data.invite_id)
        if not invite or invite.tenant_id != data.tenant_id:
            raise ResourceNotFoundException("Convite não encontrado nesta instituição.")

        # 3. Valida se o convite já foi aceito ou revogado
        if invite.is_accepted:
            raise BusinessRuleException("Não é possível revogar um convite que já foi aceito.")

        if invite.is_revoked:
            raise BusinessRuleException("Este convite já foi revogado.")

        # 4. Revoga o convite
        invite.revoked_at = datetime.now(timezone.utc)
        return await self.invite_repo.save(invite)
