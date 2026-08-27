from dataclasses import dataclass
from uuid import UUID

from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository
from modules.user.domain.entities.user import User
from security.jwt import create_access_token


@dataclass
class SwitchTenantInput:
    user: User
    tenant_id: UUID


@dataclass
class SwitchTenantOutput:
    access_token: str
    token_type: str = "bearer"


class SwitchTenantUseCase:

    def __init__(self, member_repo: TenantMemberRepository) -> None:
        self.member_repo = member_repo

    async def execute(self, data: SwitchTenantInput) -> SwitchTenantOutput:
        membership = await self.member_repo.find_by_tenant_and_user(
            tenant_id=data.tenant_id,
            user_id=data.user.id,
        )

        if not membership:
            raise ValueError("Você não é membro desta instituição/tenant.")

        # Gera o JWT enriquecido com o contexto da tenant ativa e a role que o usuário possui nela
        token = create_access_token(
            user_id=data.user.id,
            tenant_id=data.tenant_id,
            role=membership.role.value,
        )

        return SwitchTenantOutput(access_token=token)
