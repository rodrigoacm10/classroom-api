from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.tenant.application.use_cases.list_tenant_invites import (
    ListTenantInvitesInput,
    ListTenantInvitesUseCase,
)
from modules.tenant.domain.entities.tenant_invite import TenantInvite
from shared.enums.user_role import UserRole
from shared.exceptions import ResourceNotFoundException
from shared.pagination import PaginationParams
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_tenant_invite_repository import FakeTenantInviteRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestListTenantInvitesUseCase:

    async def test_list_tenant_invites_success(self):
        """Deve listar convites da tenant com suporte a paginação."""
        tenant_repo = FakeTenantRepository()
        invite_repo = FakeTenantInviteRepository()
        use_case = ListTenantInvitesUseCase(tenant_repo=tenant_repo, invite_repo=invite_repo)

        tenant = TenantFactory.make(name="Escola Teste")
        tenant_repo.seed(tenant)

        now = datetime.now(timezone.utc)
        inv1 = TenantInvite(tenant_id=tenant.id, email="a@teste.com", role=UserRole.ALUNO, expires_at=now + timedelta(hours=24))
        inv2 = TenantInvite(tenant_id=tenant.id, email="b@teste.com", role=UserRole.PROFESSOR, expires_at=now + timedelta(hours=24))
        invite_repo.seed(inv1)
        invite_repo.seed(inv2)

        result = await use_case.execute(
            ListTenantInvitesInput(
                tenant_id=tenant.id,
                pagination=PaginationParams(page=1, page_size=10),
            )
        )

        assert result.total == 2
        assert len(result.items) == 2
        emails = {item.email for item in result.items}
        assert "a@teste.com" in emails
        assert "b@teste.com" in emails

    async def test_list_tenant_invites_tenant_not_found(self):
        """Deve lançar ResourceNotFoundException caso a tenant não exista."""
        tenant_repo = FakeTenantRepository()
        invite_repo = FakeTenantInviteRepository()
        use_case = ListTenantInvitesUseCase(tenant_repo=tenant_repo, invite_repo=invite_repo)

        with pytest.raises(ResourceNotFoundException, match="Tenant não encontrada."):
            await use_case.execute(ListTenantInvitesInput(tenant_id=uuid4()))

    async def test_list_tenant_invites_filter_by_status(self):
        """Deve filtrar convites por status (pending, accepted, revoked, expired)."""
        tenant_repo = FakeTenantRepository()
        invite_repo = FakeTenantInviteRepository()
        use_case = ListTenantInvitesUseCase(tenant_repo=tenant_repo, invite_repo=invite_repo)

        tenant = TenantFactory.make(name="Escola Status")
        tenant_repo.seed(tenant)

        now = datetime.now(timezone.utc)
        pending_inv = TenantInvite(tenant_id=tenant.id, email="pending@teste.com", role=UserRole.ALUNO, expires_at=now + timedelta(hours=24))
        accepted_inv = TenantInvite(tenant_id=tenant.id, email="accepted@teste.com", role=UserRole.ALUNO, expires_at=now + timedelta(hours=24), accepted_at=now)
        revoked_inv = TenantInvite(tenant_id=tenant.id, email="revoked@teste.com", role=UserRole.ALUNO, expires_at=now + timedelta(hours=24), revoked_at=now)
        expired_inv = TenantInvite(tenant_id=tenant.id, email="expired@teste.com", role=UserRole.ALUNO, expires_at=now - timedelta(hours=1))

        for inv in [pending_inv, accepted_inv, revoked_inv, expired_inv]:
            invite_repo.seed(inv)

        page_pending = await use_case.execute(ListTenantInvitesInput(tenant_id=tenant.id, status="pending"))
        assert page_pending.total == 1
        assert page_pending.items[0].email == "pending@teste.com"

        page_accepted = await use_case.execute(ListTenantInvitesInput(tenant_id=tenant.id, status="accepted"))
        assert page_accepted.total == 1
        assert page_accepted.items[0].email == "accepted@teste.com"

        page_revoked = await use_case.execute(ListTenantInvitesInput(tenant_id=tenant.id, status="revoked"))
        assert page_revoked.total == 1
        assert page_revoked.items[0].email == "revoked@teste.com"

        page_expired = await use_case.execute(ListTenantInvitesInput(tenant_id=tenant.id, status="expired"))
        assert page_expired.total == 1
        assert page_expired.items[0].email == "expired@teste.com"

    async def test_list_tenant_invites_filter_by_role_and_search(self):
        """Deve filtrar convites por role e busca por e-mail."""
        tenant_repo = FakeTenantRepository()
        invite_repo = FakeTenantInviteRepository()
        use_case = ListTenantInvitesUseCase(tenant_repo=tenant_repo, invite_repo=invite_repo)

        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        now = datetime.now(timezone.utc)
        inv1 = TenantInvite(tenant_id=tenant.id, email="aluno_carlos@escola.com", role=UserRole.ALUNO, expires_at=now + timedelta(hours=24))
        inv2 = TenantInvite(tenant_id=tenant.id, email="prof_ana@escola.com", role=UserRole.PROFESSOR, expires_at=now + timedelta(hours=24))
        invite_repo.seed(inv1)
        invite_repo.seed(inv2)

        res_role = await use_case.execute(ListTenantInvitesInput(tenant_id=tenant.id, role=UserRole.PROFESSOR))
        assert res_role.total == 1
        assert res_role.items[0].email == "prof_ana@escola.com"

        res_search = await use_case.execute(ListTenantInvitesInput(tenant_id=tenant.id, search="carlos"))
        assert res_search.total == 1
        assert res_search.items[0].email == "aluno_carlos@escola.com"
