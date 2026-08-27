from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from config.settings import settings
from infra.email.resend_client import send_invite_email
from modules.tenant.domain.entities.tenant_invite import TenantInvite
from modules.tenant.domain.repositories.tenant_invite_repository import TenantInviteRepository
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from modules.user.domain.entities.user import User
from modules.user.domain.repositories.user_repository import UserRepository
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class SendInviteInput:
    tenant_id: UUID
    email: str
    role: UserRole
    invited_by: User


class SendInviteUseCase:

    def __init__(
        self,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
        invite_repo: TenantInviteRepository,
        user_repo: UserRepository | None = None,
        expire_hours: int = settings.invite_expire_hours,
        frontend_url: str = settings.frontend_url,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo
        self.invite_repo = invite_repo
        self.user_repo = user_repo
        self.expire_hours = expire_hours
        self.frontend_url = frontend_url

    async def execute(self, data: SendInviteInput) -> TenantInvite:
        # 1. Verifica se a tenant existe e não está deletada
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        # 2. Verifica se o convidado já é membro da tenant (se já tiver conta no sistema)
        if self.user_repo:
            invited_user = await self.user_repo.find_by_email(data.email)
            if invited_user:
                existing_member = await self.member_repo.find_by_tenant_and_user(
                    tenant_id=data.tenant_id,
                    user_id=invited_user.id,
                )
                if existing_member:
                    raise BusinessRuleException("Este usuário já é membro desta instituição.")

        # 3. Verifica se já existe um invite pendente para este e-mail nesta tenant
        existing_invite = await self.invite_repo.find_by_email_and_tenant(
            email=data.email, tenant_id=data.tenant_id
        )
        if existing_invite and existing_invite.is_pending:
            raise BusinessRuleException("Já existe um convite pendente para este e-mail nesta instituição.")

        # 4. Cria o convite
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self.expire_hours)
        invite = TenantInvite(
            tenant_id=data.tenant_id,
            invited_by=data.invited_by.id,
            email=data.email,
            role=data.role,
            expires_at=expires_at,
        )

        saved_invite = await self.invite_repo.save(invite)

        # 5. Monta o link e dispara o e-mail de convite
        invite_link = f"{self.frontend_url}/invites/accept?token={saved_invite.token}"
        send_invite_email(
            to_email=data.email,
            tenant_name=tenant.name,
            inviter_name=data.invited_by.name,
            role=data.role.value,
            invite_link=invite_link,
            expires_in_hours=self.expire_hours,
        )

        return saved_invite
