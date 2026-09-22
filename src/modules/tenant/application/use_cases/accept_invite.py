from datetime import datetime, timezone

from modules.tenant.domain.entities.tenant_member import TenantMember
from modules.tenant.domain.repositories.tenant_invite_repository import TenantInviteRepository
from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository
from modules.user.domain.entities.user import User
from shared.exceptions import (
    BusinessRuleException,
    ForbiddenException,
    ResourceNotFoundException,
)


class AcceptInviteUseCase:

    def __init__(
        self,
        invite_repo: TenantInviteRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.invite_repo = invite_repo
        self.member_repo = member_repo

    async def execute(self, token: str, user: User) -> TenantMember:
        # 1. Busca o convite
        invite = await self.invite_repo.find_by_token(token)
        if not invite:
            raise ResourceNotFoundException("Convite não encontrado.")

        # 2. Valida status
        if invite.is_accepted:
            raise BusinessRuleException("Este convite já foi aceito.")

        if invite.is_revoked:
            raise BusinessRuleException("Este convite foi revogado pelo administrador.")

        if invite.is_expired:
            raise BusinessRuleException("Este convite está expirado.")

        # 3. Valida se o e-mail do usuário autenticado é o mesmo do convite
        if user.email.lower() != invite.email.lower():
            raise ForbiddenException("Este convite foi enviado para outro endereço de e-mail.")

        # 4. Verifica se já é membro (idempotência/race condition)
        existing_member = await self.member_repo.find_by_tenant_and_user(
            tenant_id=invite.tenant_id,
            user_id=user.id,
        )
        if existing_member:
            invite.accepted_at = datetime.now(timezone.utc)
            await self.invite_repo.save(invite)
            return existing_member

        # 5. Vincula o usuário como membro do tenant
        member = TenantMember(
            tenant_id=invite.tenant_id,
            user_id=user.id,
            role=invite.role,
        )
        saved_member = await self.member_repo.save(member)

        # 6. Marca o convite como aceito
        invite.accepted_at = datetime.now(timezone.utc)
        await self.invite_repo.save(invite)

        return saved_member
