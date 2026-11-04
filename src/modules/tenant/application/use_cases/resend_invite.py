import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from config.settings import settings
from infra.tasks.email_tasks import send_invite_email_task
from modules.tenant.domain.entities.tenant_invite import TenantInvite
from modules.tenant.domain.repositories.tenant_invite_repository import TenantInviteRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from modules.user.domain.entities.user import User
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class ResendInviteInput:
    tenant_id: UUID
    invite_id: UUID
    resender: User


class ResendInviteUseCase:
    def __init__(
        self,
        tenant_repo: TenantRepository,
        invite_repo: TenantInviteRepository,
        expire_hours: int = settings.invite_expire_hours,
        frontend_url: str = settings.frontend_url,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.invite_repo = invite_repo
        self.expire_hours = expire_hours
        self.frontend_url = frontend_url

    async def execute(self, data: ResendInviteInput) -> TenantInvite:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        invite = await self.invite_repo.find_by_id(data.invite_id)
        if not invite or invite.tenant_id != data.tenant_id:
            raise ResourceNotFoundException("Convite não encontrado nesta instituição.")

        if invite.is_accepted:
            raise BusinessRuleException("Não é possível reenviar um convite que já foi aceito.")

        # Renova o prazo de expiração a partir do momento do reenvio
        invite.expires_at = datetime.now(timezone.utc) + timedelta(hours=self.expire_hours)
        # Se estava revogado, reativa para pendente
        invite.revoked_at = None
        # Gera novo token de ativação seguro
        invite.token = secrets.token_urlsafe(32)

        saved = await self.invite_repo.save(invite)
        saved.tenant_name = tenant.name

        # Enfileira o disparo assíncrono do e-mail de convite com o novo link via Celery
        invite_link = f"{self.frontend_url}/invites/accept?token={saved.token}"
        send_invite_email_task.delay(
            to_email=saved.email,
            tenant_name=tenant.name,
            inviter_name=data.resender.name,
            role=saved.role.value,
            invite_link=invite_link,
            expires_in_hours=self.expire_hours,
        )

        return saved
