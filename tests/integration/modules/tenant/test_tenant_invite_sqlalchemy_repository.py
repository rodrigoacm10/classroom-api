from datetime import datetime, timedelta, timezone

import pytest

from modules.tenant.domain.entities.tenant_invite import TenantInvite
from modules.tenant.infra.repositories.tenant_invite_sqlalchemy_repository import (
    TenantInviteSQLAlchemyRepository,
)
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory


@pytest.mark.asyncio
class TestTenantInviteSQLAlchemyRepository:
    """
    Testes de integração para TenantInviteSQLAlchemyRepository no PostgreSQL real.
    """

    @pytest.fixture(autouse=True)
    def setup(self, session) -> None:
        self.repository = TenantInviteSQLAlchemyRepository(session=session)
        self.session = session

    async def test_save_and_find_by_token_and_id(self) -> None:
        """Persiste um convite e realiza busca por token e por ID no Postgres."""
        tenant = await TenantFactory.create(self.session)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        invite = TenantInvite(
            tenant_id=tenant.id,
            email="teste_postgres@escola.com",
            role=UserRole.PROFESSOR,
            expires_at=expires_at,
            token="token-integ-123",
        )

        saved = await self.repository.save(invite)
        assert saved.id == invite.id
        assert saved.token == "token-integ-123"

        found_by_token = await self.repository.find_by_token("token-integ-123")
        assert found_by_token is not None
        assert found_by_token.id == invite.id

        found_by_id = await self.repository.find_by_id(invite.id)
        assert found_by_id is not None
        assert found_by_id.email == "teste_postgres@escola.com"

    async def test_find_by_email_and_tenant_filters_accepted_and_revoked(self) -> None:
        """find_by_email_and_tenant só deve retornar convites não-aceitos e não-revogados."""
        tenant = await TenantFactory.create(self.session)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        active_invite = TenantInvite(
            tenant_id=tenant.id,
            email="ativo@escola.com",
            role=UserRole.ALUNO,
            expires_at=expires_at,
        )
        accepted_invite = TenantInvite(
            tenant_id=tenant.id,
            email="aceito@escola.com",
            role=UserRole.ALUNO,
            expires_at=expires_at,
            accepted_at=datetime.now(timezone.utc),
        )
        revoked_invite = TenantInvite(
            tenant_id=tenant.id,
            email="revogado@escola.com",
            role=UserRole.ALUNO,
            expires_at=expires_at,
            revoked_at=datetime.now(timezone.utc),
        )

        await self.repository.save(active_invite)
        await self.repository.save(accepted_invite)
        await self.repository.save(revoked_invite)

        # Ativo deve ser encontrado
        found_active = await self.repository.find_by_email_and_tenant("ativo@escola.com", tenant.id)
        assert found_active is not None
        assert found_active.id == active_invite.id

        # Aceito e Revogado devem retornar None
        assert await self.repository.find_by_email_and_tenant("aceito@escola.com", tenant.id) is None
        assert await self.repository.find_by_email_and_tenant("revogado@escola.com", tenant.id) is None
