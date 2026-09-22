import uuid

import pytest

from modules.auth.application.use_cases.switch_tenant import (
    SwitchTenantInput,
    SwitchTenantUseCase,
)
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


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
    - Tenant está desativada → ValueError
    - Tenant está deletada → ValueError
    """

    def setup_method(self) -> None:
        self.member_repo = FakeTenantMemberRepository()
        self.tenant_repo = FakeTenantRepository()
        self.use_case = SwitchTenantUseCase(
            member_repo=self.member_repo,
            tenant_repo=self.tenant_repo,
        )

    async def test_switch_tenant_returns_token_when_user_is_member(self) -> None:
        """Usuário com membership ativa na tenant → retorna access_token."""
        user = UserFactory.make()
        tenant = TenantFactory.make(active=True, deleted=False)
        self.tenant_repo.seed(tenant)

        member = _make_member(tenant_id=tenant.id, user_id=user.id)
        self.member_repo.seed(member)

        result = await self.use_case.execute(
            SwitchTenantInput(user=user, tenant_id=tenant.id)
        )

        assert result.access_token
        assert result.token_type == "bearer"

    async def test_switch_tenant_raises_when_user_is_not_member(self) -> None:
        """Usuário sem membership na tenant informada → ValueError."""
        user = UserFactory.make()
        tenant = TenantFactory.make(active=True, deleted=False)
        self.tenant_repo.seed(tenant)

        with pytest.raises(ValueError, match="não é membro"):
            await self.use_case.execute(
                SwitchTenantInput(user=user, tenant_id=tenant.id)
            )

    async def test_switch_tenant_raises_when_membership_belongs_to_different_tenant(
        self,
    ) -> None:
        """Usuário é membro de outra tenant, não da solicitada → ValueError."""
        user = UserFactory.make()
        correct_tenant = TenantFactory.make()
        wrong_tenant = TenantFactory.make()

        self.tenant_repo.seed(correct_tenant)
        self.tenant_repo.seed(wrong_tenant)

        member = _make_member(tenant_id=correct_tenant.id, user_id=user.id)
        self.member_repo.seed(member)

        with pytest.raises(ValueError, match="não é membro"):
            await self.use_case.execute(
                SwitchTenantInput(user=user, tenant_id=wrong_tenant.id)
            )

    async def test_switch_tenant_raises_when_tenant_is_inactive(self) -> None:
        """Usuário tenta acessar tenant desativada → ValueError."""
        user = UserFactory.make()
        tenant = TenantFactory.make(active=False, deleted=False)
        self.tenant_repo.seed(tenant)

        member = _make_member(tenant_id=tenant.id, user_id=user.id)
        self.member_repo.seed(member)

        with pytest.raises(ValueError, match="desativada"):
            await self.use_case.execute(
                SwitchTenantInput(user=user, tenant_id=tenant.id)
            )

    async def test_switch_tenant_raises_when_tenant_is_deleted(self) -> None:
        """Usuário tenta acessar tenant deletada → ValueError."""
        user = UserFactory.make()
        tenant = TenantFactory.make(active=True, deleted=True)
        self.tenant_repo.seed(tenant)

        member = _make_member(tenant_id=tenant.id, user_id=user.id)
        self.member_repo.seed(member)

        with pytest.raises(ValueError, match="não encontrada"):
            await self.use_case.execute(
                SwitchTenantInput(user=user, tenant_id=tenant.id)
            )
