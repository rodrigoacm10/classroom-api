from dataclasses import dataclass
from typing import Literal

from modules.tenant.domain.entities.tenant_invite import TenantInvite
from modules.tenant.domain.repositories.tenant_invite_repository import TenantInviteRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class GetInviteOutput:
    invite: TenantInvite
    tenant_name: str
    status: Literal["pending", "accepted", "expired", "revoked"]


class GetInviteUseCase:

    def __init__(
        self,
        invite_repo: TenantInviteRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.invite_repo = invite_repo
        self.tenant_repo = tenant_repo

    async def execute(self, token: str) -> GetInviteOutput:
        invite = await self.invite_repo.find_by_token(token)
        if not invite:
            raise ResourceNotFoundException("Convite não encontrado.")

        tenant = await self.tenant_repo.find_by_id(invite.tenant_id, include_deleted=True)
        tenant_name = tenant.name if tenant else "Instituição Desconhecida"

        if invite.is_revoked:
            status_str: Literal["pending", "accepted", "expired", "revoked"] = "revoked"
        elif invite.is_accepted:
            status_str = "accepted"
        elif invite.is_expired:
            status_str = "expired"
        else:
            status_str = "pending"

        return GetInviteOutput(
            invite=invite,
            tenant_name=tenant_name,
            status=status_str,
        )
