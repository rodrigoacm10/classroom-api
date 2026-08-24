from dataclasses import dataclass
from uuid import UUID

from modules.user.domain.entities.user import User


@dataclass
class SwitchTenantInput:
    user: User
    tenant_id: UUID


@dataclass
class SwitchTenantOutput:
    access_token: str
    token_type: str = "bearer"


class SwitchTenantUseCase:
    """
    Verifica se o usuário é membro da tenant informada e,
    se for, retorna um JWT enriquecido com tenant_id + role.

    Depende de TenantMemberRepository (Task 2).
    Deixe como NotImplementedError até a Task 2 ser concluída.
    """

    async def execute(self, data: SwitchTenantInput) -> SwitchTenantOutput:
        # TODO (Task 2): buscar TenantMember(user_id=data.user.id, tenant_id=data.tenant_id)
        # Se não encontrar → raise ValueError("Usuário não é membro desta tenant.")
        # role = member.role

        raise NotImplementedError("Aguardando Task 2 — módulo tenant/")
