from dataclasses import dataclass
from uuid import UUID

from modules.notification.domain.entities.fcm_token import FCMToken
from modules.notification.domain.repositories.fcm_token_repository import FCMTokenRepository
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException


@dataclass
class RegisterFCMTokenInput:
    tenant_id: UUID
    user_id: UUID
    user_role: UserRole | None
    device_id: str
    fcm_token: str
    platform: str
    app_version: str | None = None


class RegisterFCMTokenUseCase:

    def __init__(
        self,
        fcm_token_repo: FCMTokenRepository,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.fcm_token_repo = fcm_token_repo
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: RegisterFCMTokenInput) -> FCMToken:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        member = await self.member_repo.find_by_tenant_and_user(data.tenant_id, data.user_id)
        if not member or getattr(member, "deleted", False):
            raise ForbiddenException("Usuário não é membro desta instituição.")

        token = FCMToken(
            user_id=data.user_id,
            device_id=data.device_id,
            fcm_token=data.fcm_token,
            platform=data.platform,
            app_version=data.app_version,
        )

        return await self.fcm_token_repo.upsert(token)
