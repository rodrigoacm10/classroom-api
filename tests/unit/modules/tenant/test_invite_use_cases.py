from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from modules.tenant.application.use_cases.accept_invite import AcceptInviteUseCase
from modules.tenant.application.use_cases.get_invite import GetInviteUseCase
from modules.tenant.application.use_cases.send_invite import (
    SendInviteInput,
    SendInviteUseCase,
)
from modules.tenant.domain.entities.tenant_invite import TenantInvite
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from shared.exceptions import (
    BusinessRuleException,
    ForbiddenException,
    ResourceNotFoundException,
)
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory
from tests.unit.fakes.fake_tenant_invite_repository import FakeTenantInviteRepository
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository
from tests.unit.fakes.fake_user_repository import FakeUserRepository


@pytest.mark.asyncio
class TestSendInviteUseCase:

    async def test_send_invite_success(self):
        """Deve criar e retornar um convite com sucesso quando os dados forem válidos."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        invite_repo = FakeTenantInviteRepository()

        admin_user = UserFactory.make(name="Admin User")
        tenant = TenantFactory.make(name="Escola Beta")
        tenant_repo.seed(tenant)

        use_case = SendInviteUseCase(
            tenant_repo=tenant_repo,
            member_repo=member_repo,
            invite_repo=invite_repo,
        )

        with patch("modules.tenant.application.use_cases.send_invite.send_invite_email"):
            invite = await use_case.execute(
                SendInviteInput(
                    tenant_id=tenant.id,
                    email="professor@escola.com",
                    role=UserRole.PROFESSOR,
                    invited_by=admin_user,
                )
            )

        assert invite.id is not None
        assert invite.tenant_id == tenant.id
        assert invite.email == "professor@escola.com"
        assert invite.role == UserRole.PROFESSOR
        assert invite.invited_by == admin_user.id
        assert invite.is_pending is True

    async def test_send_invite_tenant_not_found_raises(self):
        """Deve lançar ResourceNotFoundException se a tenant informada não existir."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        invite_repo = FakeTenantInviteRepository()
        admin_user = UserFactory.make()

        use_case = SendInviteUseCase(
            tenant_repo=tenant_repo,
            member_repo=member_repo,
            invite_repo=invite_repo,
        )

        dummy_tenant = TenantFactory.make()
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                SendInviteInput(
                    tenant_id=dummy_tenant.id,
                    email="prof@escola.com",
                    role=UserRole.PROFESSOR,
                    invited_by=admin_user,
                )
            )

    async def test_send_invite_already_member_raises(self):
        """Deve lançar BusinessRuleException se o usuário do e-mail já for membro da tenant."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        invite_repo = FakeTenantInviteRepository()
        user_repo = FakeUserRepository()

        admin_user = UserFactory.make()
        existing_user = UserFactory.make(email="existente@escola.com")
        user_repo.seed(existing_user)

        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        member_repo.seed(
            TenantMember(tenant_id=tenant.id, user_id=existing_user.id, role=UserRole.ALUNO)
        )

        use_case = SendInviteUseCase(
            tenant_repo=tenant_repo,
            member_repo=member_repo,
            invite_repo=invite_repo,
            user_repo=user_repo,
        )

        with pytest.raises(BusinessRuleException, match="já é membro"):
            await use_case.execute(
                SendInviteInput(
                    tenant_id=tenant.id,
                    email=existing_user.email,
                    role=UserRole.PROFESSOR,
                    invited_by=admin_user,
                )
            )

    async def test_send_invite_pending_invite_exists_raises(self):
        """Deve lançar BusinessRuleException se já existir um convite pendente para o mesmo e-mail."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        invite_repo = FakeTenantInviteRepository()

        admin_user = UserFactory.make()
        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        existing_invite = TenantInvite(
            tenant_id=tenant.id,
            email="pendente@escola.com",
            role=UserRole.PROFESSOR,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        invite_repo.seed(existing_invite)

        use_case = SendInviteUseCase(
            tenant_repo=tenant_repo,
            member_repo=member_repo,
            invite_repo=invite_repo,
        )

        with pytest.raises(BusinessRuleException, match="Já existe um convite pendente"):
            await use_case.execute(
                SendInviteInput(
                    tenant_id=tenant.id,
                    email="pendente@escola.com",
                    role=UserRole.PROFESSOR,
                    invited_by=admin_user,
                )
            )


@pytest.mark.asyncio
class TestGetInviteUseCase:

    async def test_get_invite_success_pending(self):
        """Deve retornar os detalhes do convite quando o convite estiver com status pendente."""
        invite_repo = FakeTenantInviteRepository()
        tenant_repo = FakeTenantRepository()

        tenant = TenantFactory.make(name="Escola Gama")
        tenant_repo.seed(tenant)

        invite = TenantInvite(
            tenant_id=tenant.id,
            email="convidado@escola.com",
            role=UserRole.PROFESSOR,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        invite_repo.seed(invite)

        use_case = GetInviteUseCase(invite_repo=invite_repo, tenant_repo=tenant_repo)
        result = await use_case.execute(invite.token)

        assert result.tenant_name == "Escola Gama"
        assert result.status == "pending"
        assert result.invite.token == invite.token

    async def test_get_invite_success_expired(self):
        """Deve retornar status expirado quando o convite tiver excedido a data de expiração."""
        invite_repo = FakeTenantInviteRepository()
        tenant_repo = FakeTenantRepository()

        tenant = TenantFactory.make(name="Escola Expirada")
        tenant_repo.seed(tenant)

        invite = TenantInvite(
            tenant_id=tenant.id,
            email="expirado@escola.com",
            role=UserRole.ALUNO,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        invite_repo.seed(invite)

        use_case = GetInviteUseCase(invite_repo=invite_repo, tenant_repo=tenant_repo)
        result = await use_case.execute(invite.token)

        assert result.status == "expired"

    async def test_get_invite_not_found_raises(self):
        """Deve lançar ResourceNotFoundException se o token informado não for encontrado."""
        invite_repo = FakeTenantInviteRepository()
        tenant_repo = FakeTenantRepository()

        use_case = GetInviteUseCase(invite_repo=invite_repo, tenant_repo=tenant_repo)
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute("token-inexistente")


@pytest.mark.asyncio
class TestAcceptInviteUseCase:

    async def test_accept_invite_success(self):
        """Deve aceitar o convite, criar o vinculo de membro e marcar o convite como aceito."""
        invite_repo = FakeTenantInviteRepository()
        member_repo = FakeTenantMemberRepository()

        invited_user = UserFactory.make(email="convidado@escola.com")
        tenant_id = TenantFactory.make().id

        invite = TenantInvite(
            tenant_id=tenant_id,
            email="convidado@escola.com",
            role=UserRole.PROFESSOR,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        invite_repo.seed(invite)

        use_case = AcceptInviteUseCase(invite_repo=invite_repo, member_repo=member_repo)
        member = await use_case.execute(token=invite.token, user=invited_user)

        assert member.tenant_id == tenant_id
        assert member.user_id == invited_user.id
        assert member.role == UserRole.PROFESSOR

        updated_invite = await invite_repo.find_by_token(invite.token)
        assert updated_invite is not None
        assert updated_invite.is_accepted is True

    async def test_accept_invite_expired_raises(self):
        """Deve lançar BusinessRuleException ao tentar aceitar um convite que já expirou."""
        invite_repo = FakeTenantInviteRepository()
        member_repo = FakeTenantMemberRepository()

        invited_user = UserFactory.make(email="expirado@escola.com")
        tenant_id = TenantFactory.make().id

        invite = TenantInvite(
            tenant_id=tenant_id,
            email="expirado@escola.com",
            role=UserRole.ALUNO,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        invite_repo.seed(invite)

        use_case = AcceptInviteUseCase(invite_repo=invite_repo, member_repo=member_repo)
        with pytest.raises(BusinessRuleException, match="expirado"):
            await use_case.execute(token=invite.token, user=invited_user)

    async def test_accept_invite_different_email_raises(self):
        """Deve lançar ForbiddenException se o e-mail do usuário autenticado for diferente do convite."""
        invite_repo = FakeTenantInviteRepository()
        member_repo = FakeTenantMemberRepository()

        user_wrong_email = UserFactory.make(email="outro@escola.com")
        tenant_id = TenantFactory.make().id

        invite = TenantInvite(
            tenant_id=tenant_id,
            email="alvo@escola.com",
            role=UserRole.ALUNO,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        invite_repo.seed(invite)

        use_case = AcceptInviteUseCase(invite_repo=invite_repo, member_repo=member_repo)
        with pytest.raises(ForbiddenException, match="outro endereço de e-mail"):
            await use_case.execute(token=invite.token, user=user_wrong_email)


@pytest.mark.asyncio
class TestRevokeInviteUseCase:

    async def test_revoke_invite_success(self):
        """Deve revogar um convite pendente com sucesso."""
        from modules.tenant.application.use_cases.revoke_invite import (
            RevokeInviteInput,
            RevokeInviteUseCase,
        )

        tenant_repo = FakeTenantRepository()
        invite_repo = FakeTenantInviteRepository()

        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        invite = TenantInvite(
            tenant_id=tenant.id,
            email="revogar@escola.com",
            role=UserRole.PROFESSOR,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        invite_repo.seed(invite)

        use_case = RevokeInviteUseCase(tenant_repo=tenant_repo, invite_repo=invite_repo)
        revoked_invite = await use_case.execute(
            RevokeInviteInput(tenant_id=tenant.id, invite_id=invite.id)
        )

        assert revoked_invite.is_revoked is True
        assert revoked_invite.is_pending is False

    async def test_revoke_already_accepted_raises(self):
        """Deve lançar BusinessRuleException ao tentar revogar um convite que já foi aceito."""
        from modules.tenant.application.use_cases.revoke_invite import (
            RevokeInviteInput,
            RevokeInviteUseCase,
        )

        tenant_repo = FakeTenantRepository()
        invite_repo = FakeTenantInviteRepository()

        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        invite = TenantInvite(
            tenant_id=tenant.id,
            email="aceito@escola.com",
            role=UserRole.PROFESSOR,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            accepted_at=datetime.now(timezone.utc),
        )
        invite_repo.seed(invite)

        use_case = RevokeInviteUseCase(tenant_repo=tenant_repo, invite_repo=invite_repo)
        with pytest.raises(BusinessRuleException, match="já foi aceito"):
            await use_case.execute(RevokeInviteInput(tenant_id=tenant.id, invite_id=invite.id))
