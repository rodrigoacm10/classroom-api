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

    async def test_find_by_tenant_id_paginated_with_pagination_and_multi_tenant(self) -> None:
        """Deve paginar os convites por offset e isolar registros entre tenants."""
        from shared.pagination import PaginationParams

        tenant_a = await TenantFactory.create(self.session)
        tenant_b = await TenantFactory.create(self.session)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        inv_a1 = TenantInvite(tenant_id=tenant_a.id, email="a1@escola.com", role=UserRole.ALUNO, expires_at=expires_at)
        inv_a2 = TenantInvite(tenant_id=tenant_a.id, email="a2@escola.com", role=UserRole.ALUNO, expires_at=expires_at)
        inv_a3 = TenantInvite(tenant_id=tenant_a.id, email="a3@escola.com", role=UserRole.ALUNO, expires_at=expires_at)
        inv_b1 = TenantInvite(tenant_id=tenant_b.id, email="b1@escola.com", role=UserRole.ALUNO, expires_at=expires_at)

        for inv in [inv_a1, inv_a2, inv_a3, inv_b1]:
            await self.repository.save(inv)

        page1 = await self.repository.find_by_tenant_id_paginated(
            tenant_id=tenant_a.id,
            pagination=PaginationParams(page=1, page_size=2),
        )
        assert page1.total == 3
        assert len(page1.items) == 2
        assert page1.pages == 2

        page2 = await self.repository.find_by_tenant_id_paginated(
            tenant_id=tenant_a.id,
            pagination=PaginationParams(page=2, page_size=2),
        )
        assert page2.total == 3
        assert len(page2.items) == 1

        # Tenant B isolation check
        page_b = await self.repository.find_by_tenant_id_paginated(
            tenant_id=tenant_b.id,
            pagination=PaginationParams(page=1, page_size=10),
        )
        assert page_b.total == 1
        assert page_b.items[0].email == "b1@escola.com"

    async def test_find_by_tenant_id_paginated_filters_by_status(self) -> None:
        """Deve filtrar convites no banco pelos status 'pending', 'accepted', 'revoked', 'expired'."""
        from shared.pagination import PaginationParams

        tenant = await TenantFactory.create(self.session)
        now = datetime.now(timezone.utc)

        pending = TenantInvite(tenant_id=tenant.id, email="p@escola.com", role=UserRole.ALUNO, expires_at=now + timedelta(hours=24))
        accepted = TenantInvite(tenant_id=tenant.id, email="acc@escola.com", role=UserRole.ALUNO, expires_at=now + timedelta(hours=24), accepted_at=now)
        revoked = TenantInvite(tenant_id=tenant.id, email="rev@escola.com", role=UserRole.ALUNO, expires_at=now + timedelta(hours=24), revoked_at=now)
        expired = TenantInvite(tenant_id=tenant.id, email="exp@escola.com", role=UserRole.ALUNO, expires_at=now - timedelta(hours=1))

        for inv in [pending, accepted, revoked, expired]:
            await self.repository.save(inv)

        pagination = PaginationParams(page=1, page_size=10)

        res_pending = await self.repository.find_by_tenant_id_paginated(tenant.id, pagination=pagination, status="pending")
        assert res_pending.total == 1
        assert res_pending.items[0].email == "p@escola.com"

        res_accepted = await self.repository.find_by_tenant_id_paginated(tenant.id, pagination=pagination, status="accepted")
        assert res_accepted.total == 1
        assert res_accepted.items[0].email == "acc@escola.com"

        res_revoked = await self.repository.find_by_tenant_id_paginated(tenant.id, pagination=pagination, status="revoked")
        assert res_revoked.total == 1
        assert res_revoked.items[0].email == "rev@escola.com"

        res_expired = await self.repository.find_by_tenant_id_paginated(tenant.id, pagination=pagination, status="expired")
        assert res_expired.total == 1
        assert res_expired.items[0].email == "exp@escola.com"
