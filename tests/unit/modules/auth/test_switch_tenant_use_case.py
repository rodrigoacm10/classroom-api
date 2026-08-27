import uuid

import pytest

from modules.auth.application.use_cases.switch_tenant import (
    SwitchTenantInput,
    SwitchTenantUseCase,
)
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from tests.factories.user_factory import UserFactory
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository


def _make_member(tenant_id: uuid.UUID, user_id: uuid.UUID) -> TenantMember:
    """Helper que cria um TenantMember com role padrão de PROFESSOR."""
    return TenantMember(
        tenant_id=tenant_id,
        user_id=user_id,
        role=UserRole.PROFESSOR,
    )


class TestSwitchTenantUseCase:
    """Testes unitários para SwitchTenantUseCase.

    Regras validadas:
    - Usuário é membro da tenant → retorna access_token enriquecido com tenant_id + role
    - Usuário NÃO é membro da tenant → ValueError
    """

    def setup_method(self) -> None:
        self.member_repo = FakeTenantMemberRepository()
        self.use_case = SwitchTenantUseCase(member_repo=self.member_repo)

    async def test_switch_tenant_returns_token_when_user_is_member(self) -> None:
        """Usuário com membership ativa na tenant → retorna access_token."""
        user = UserFactory.make()
        tenant_id = uuid.uuid4()
        member = _make_member(tenant_id=tenant_id, user_id=user.id)
        self.member_repo.seed(member)

        result = await self.use_case.execute(
            SwitchTenantInput(user=user, tenant_id=tenant_id)
        )

        assert result.access_token
        assert result.token_type == "bearer"

    async def test_switch_tenant_raises_when_user_is_not_member(self) -> None:
        """Usuário sem membership na tenant informada → ValueError."""
        user = UserFactory.make()
        tenant_id = uuid.uuid4()
        # repositório vazio: nenhuma membership cadastrada

        with pytest.raises(ValueError, match="não é membro"):
            await self.use_case.execute(
                SwitchTenantInput(user=user, tenant_id=tenant_id)
            )

    async def test_switch_tenant_raises_when_membership_belongs_to_different_tenant(
        self,
    ) -> None:
        """Usuário é membro de outra tenant, não da solicitada → ValueError."""
        user = UserFactory.make()
        correct_tenant = uuid.uuid4()
        wrong_tenant = uuid.uuid4()

        # cadastra membership para a tenant correta
        member = _make_member(tenant_id=correct_tenant, user_id=user.id)
        self.member_repo.seed(member)

        with pytest.raises(ValueError, match="não é membro"):
            await self.use_case.execute(
                SwitchTenantInput(user=user, tenant_id=wrong_tenant)
            )
