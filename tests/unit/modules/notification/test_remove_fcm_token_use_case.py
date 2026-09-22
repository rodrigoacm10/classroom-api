from uuid import uuid4

import pytest

from modules.notification.application.use_cases.register_fcm_token import (
    RegisterFCMTokenInput,
    RegisterFCMTokenUseCase,
)
from modules.notification.application.use_cases.remove_fcm_token import (
    RemoveFCMTokenInput,
    RemoveFCMTokenUseCase,
)
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_fcm_token_repository import FakeFCMTokenRepository
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestRemoveFCMTokenUseCase:
    """
    Suíte de Testes: RemoveFCMTokenUseCase
    Valida a desvinculação (remoção) de tokens FCM de um dispositivo ao efetuar logout.
    """

    async def test_remove_fcm_token_success(self):
        """Deve remover o token FCM cadastrado com sucesso quando o usuário faz logout do dispositivo."""
        fcm_token_repo = FakeFCMTokenRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        user_id = uuid4()
        member = TenantMember(tenant_id=tenant.id, user_id=user_id, role=UserRole.ALUNO)
        await member_repo.save(member)

        reg_use_case = RegisterFCMTokenUseCase(
            fcm_token_repo=fcm_token_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )
        await reg_use_case.execute(
            RegisterFCMTokenInput(
                tenant_id=tenant.id,
                user_id=user_id,
                user_role=UserRole.ALUNO,
                device_id="device-uuid-123",
                fcm_token="token-abc",
                platform="ios",
            )
        )

        remove_use_case = RemoveFCMTokenUseCase(
            fcm_token_repo=fcm_token_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        success = await remove_use_case.execute(
            RemoveFCMTokenInput(
                tenant_id=tenant.id,
                user_id=user_id,
                user_role=UserRole.ALUNO,
                device_id="device-uuid-123",
            )
        )

        assert success is True
        assert len(fcm_token_repo.tokens) == 0

    async def test_remove_fcm_token_raises_404_when_token_not_found(self):
        """Deve lançar ResourceNotFoundException (404) ao tentar remover o token de um dispositivo não cadastrado."""
        fcm_token_repo = FakeFCMTokenRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        user_id = uuid4()
        member = TenantMember(tenant_id=tenant.id, user_id=user_id, role=UserRole.ALUNO)
        await member_repo.save(member)

        use_case = RemoveFCMTokenUseCase(
            fcm_token_repo=fcm_token_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        with pytest.raises(ResourceNotFoundException, match="Token FCM não encontrado."):
            await use_case.execute(
                RemoveFCMTokenInput(
                    tenant_id=tenant.id,
                    user_id=user_id,
                    user_role=UserRole.ALUNO,
                    device_id="non-existent-device",
                )
            )

    async def test_remove_fcm_token_raises_404_when_tenant_not_found(self):
        """Deve lançar ResourceNotFoundException (404) quando a instituição informada não existir."""
        fcm_token_repo = FakeFCMTokenRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        use_case = RemoveFCMTokenUseCase(
            fcm_token_repo=fcm_token_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        with pytest.raises(ResourceNotFoundException, match="Instituição/tenant não encontrada."):
            await use_case.execute(
                RemoveFCMTokenInput(
                    tenant_id=uuid4(),
                    user_id=uuid4(),
                    user_role=UserRole.ALUNO,
                    device_id="device-1",
                )
            )

    async def test_remove_fcm_token_raises_403_when_not_member(self):
        """Deve lançar ForbiddenException (403) quando o usuário não for membro ativo da instituição."""
        fcm_token_repo = FakeFCMTokenRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        use_case = RemoveFCMTokenUseCase(
            fcm_token_repo=fcm_token_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        with pytest.raises(ForbiddenException, match="Usuário não é membro desta instituição."):
            await use_case.execute(
                RemoveFCMTokenInput(
                    tenant_id=tenant.id,
                    user_id=uuid4(),
                    user_role=UserRole.ALUNO,
                    device_id="device-1",
                )
            )
