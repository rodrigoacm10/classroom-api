from uuid import uuid4

import pytest

from modules.notification.application.use_cases.register_fcm_token import (
    RegisterFCMTokenInput,
    RegisterFCMTokenUseCase,
)
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_fcm_token_repository import FakeFCMTokenRepository
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestRegisterFCMTokenUseCase:
    """
    Suíte de Testes: RegisterFCMTokenUseCase
    Valida o cadastro e atualização (upsert) de tokens FCM de dispositivos móveis.
    """

    async def test_register_fcm_token_success(self):
        """Deve registrar um novo token FCM com metadados do dispositivo para um membro ativo da instituição."""
        fcm_token_repo = FakeFCMTokenRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        user_id = uuid4()
        member = TenantMember(tenant_id=tenant.id, user_id=user_id, role=UserRole.ALUNO)
        await member_repo.save(member)

        use_case = RegisterFCMTokenUseCase(
            fcm_token_repo=fcm_token_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        input_data = RegisterFCMTokenInput(
            tenant_id=tenant.id,
            user_id=user_id,
            user_role=UserRole.ALUNO,
            device_id="device-uuid-123",
            fcm_token="fcm-token-xyz",
            platform="android",
            app_version="1.0.0",
        )

        result = await use_case.execute(input_data)

        assert result.user_id == user_id
        assert result.device_id == "device-uuid-123"
        assert result.fcm_token == "fcm-token-xyz"
        assert result.platform == "android"
        assert result.app_version == "1.0.0"

    async def test_register_fcm_token_upsert(self):
        """Deve atualizar o token FCM quando o mesmo dispositivo se registrar novamente, sem criar registros duplicados."""
        fcm_token_repo = FakeFCMTokenRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        user_id = uuid4()
        member = TenantMember(tenant_id=tenant.id, user_id=user_id, role=UserRole.ALUNO)
        await member_repo.save(member)

        use_case = RegisterFCMTokenUseCase(
            fcm_token_repo=fcm_token_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        input_1 = RegisterFCMTokenInput(
            tenant_id=tenant.id,
            user_id=user_id,
            user_role=UserRole.ALUNO,
            device_id="device-uuid-123",
            fcm_token="token-old",
            platform="android",
        )
        await use_case.execute(input_1)

        input_2 = RegisterFCMTokenInput(
            tenant_id=tenant.id,
            user_id=user_id,
            user_role=UserRole.ALUNO,
            device_id="device-uuid-123",
            fcm_token="token-new",
            platform="android",
        )
        result = await use_case.execute(input_2)

        assert len(fcm_token_repo.tokens) == 1
        assert result.fcm_token == "token-new"

    async def test_register_fcm_token_raises_404_when_tenant_not_found(self):
        """Deve lançar ResourceNotFoundException (404) ao tentar registrar um token para uma instituição inexistente."""
        fcm_token_repo = FakeFCMTokenRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        use_case = RegisterFCMTokenUseCase(
            fcm_token_repo=fcm_token_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        with pytest.raises(ResourceNotFoundException, match="Instituição/tenant não encontrada."):
            await use_case.execute(
                RegisterFCMTokenInput(
                    tenant_id=uuid4(),
                    user_id=uuid4(),
                    user_role=UserRole.ALUNO,
                    device_id="dev-1",
                    fcm_token="token-1",
                    platform="android",
                )
            )

    async def test_register_fcm_token_raises_403_when_not_member(self):
        """Deve lançar ForbiddenException (403) quando o usuário não for membro ativo da instituição informada."""
        fcm_token_repo = FakeFCMTokenRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        use_case = RegisterFCMTokenUseCase(
            fcm_token_repo=fcm_token_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        with pytest.raises(ForbiddenException, match="Usuário não é membro desta instituição."):
            await use_case.execute(
                RegisterFCMTokenInput(
                    tenant_id=tenant.id,
                    user_id=uuid4(),
                    user_role=UserRole.ALUNO,
                    device_id="dev-1",
                    fcm_token="token-1",
                    platform="android",
                )
            )

    async def test_register_fcm_token_multi_device_support(self):
        """Deve permitir que o usuário permaneça logado em múltiplos dispositivos (celular + tablet) mantendo tokens FCM distintos ativos."""
        fcm_token_repo = FakeFCMTokenRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        user_id = uuid4()
        member = TenantMember(tenant_id=tenant.id, user_id=user_id, role=UserRole.ALUNO)
        await member_repo.save(member)

        use_case = RegisterFCMTokenUseCase(
            fcm_token_repo=fcm_token_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        # 1. Login/Registro no Celular
        mobile_input = RegisterFCMTokenInput(
            tenant_id=tenant.id,
            user_id=user_id,
            user_role=UserRole.ALUNO,
            device_id="device-mobile-uuid-111",
            fcm_token="fcm-token-mobile-aaa",
            platform="android",
            app_version="1.0.0",
        )
        mobile_result = await use_case.execute(mobile_input)

        # 2. Login/Registro no Tablet
        tablet_input = RegisterFCMTokenInput(
            tenant_id=tenant.id,
            user_id=user_id,
            user_role=UserRole.ALUNO,
            device_id="device-tablet-uuid-222",
            fcm_token="fcm-token-tablet-bbb",
            platform="ios",
            app_version="1.0.0",
        )
        tablet_result = await use_case.execute(tablet_input)

        # Valida que ambos os tokens existem para o mesmo usuário com device_ids distintos
        assert len(fcm_token_repo.tokens) == 2
        assert mobile_result.device_id != tablet_result.device_id
        assert mobile_result.fcm_token == "fcm-token-mobile-aaa"
        assert tablet_result.fcm_token == "fcm-token-tablet-bbb"
        assert fcm_token_repo.tokens[0].user_id == user_id
        assert fcm_token_repo.tokens[1].user_id == user_id
