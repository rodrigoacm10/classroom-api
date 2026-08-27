import uuid

import pytest

from modules.tenant.domain.entities.tenant import Tenant
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import (
    TenantSQLAlchemyRepository,
)
from tests.factories.tenant_factory import TenantFactory


@pytest.mark.asyncio
class TestTenantSQLAlchemyRepository:
    """
    Testes de integração para TenantSQLAlchemyRepository no PostgreSQL real.
    """

    @pytest.fixture(autouse=True)
    def setup(self, session) -> None:
        self.repository = TenantSQLAlchemyRepository(session=session)
        self.session = session

    async def test_save_and_find_by_id_success(self) -> None:
        """Persiste uma tenant no Postgres e busca por ID."""
        tenant = Tenant(name="Escola Real", slug="escola-real")

        saved = await self.repository.save(tenant)
        assert saved.id == tenant.id
        assert saved.name == "Escola Real"

        found = await self.repository.find_by_id(tenant.id)
        assert found is not None
        assert found.id == tenant.id
        assert found.slug == "escola-real"

    async def test_find_by_slug_active_and_deleted(self) -> None:
        """find_by_slug deve ignorar tenants deletadas por padrão."""
        active_tenant = await TenantFactory.create(self.session, slug="tenant-ativa", deleted=False)
        deleted_tenant = await TenantFactory.create(self.session, slug="tenant-deletada", deleted=True)

        found_active = await self.repository.find_by_slug("tenant-ativa")
        assert found_active is not None
        assert found_active.id == active_tenant.id

        found_deleted_default = await self.repository.find_by_slug("tenant-deletada")
        assert found_deleted_default is None

        found_deleted_included = await self.repository.find_by_slug("tenant-deletada", include_deleted=True)
        assert found_deleted_included is not None
        assert found_deleted_included.id == deleted_tenant.id

    async def test_find_by_id_returns_none_when_not_exists(self) -> None:
        """Busca por ID inexistente retorna None."""
        result = await self.repository.find_by_id(uuid.uuid4())
        assert result is None
