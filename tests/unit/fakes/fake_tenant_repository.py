from uuid import UUID

from modules.tenant.domain.entities.tenant import Tenant


class FakeTenantRepository:
    """
    Implementação em memória do TenantRepository.
    Satisfaz o Protocol sem tocar em banco de dados.
    Usado exclusivamente em testes unitários.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, Tenant] = {}

    async def find_by_id(self, tenant_id: UUID, include_deleted: bool = False) -> Tenant | None:
        tenant = self._store.get(tenant_id)
        if not tenant:
            return None
        if tenant.deleted and not include_deleted:
            return None
        return tenant

    async def find_by_slug(self, slug: str, include_deleted: bool = False) -> Tenant | None:
        tenant = next((t for t in self._store.values() if t.slug == slug), None)
        if not tenant:
            return None
        if tenant.deleted and not include_deleted:
            return None
        return tenant

    async def save(self, tenant: Tenant) -> Tenant:
        self._store[tenant.id] = tenant
        return tenant

    # ─── helpers de setup ────────────────────────────────────────────────────

    def seed(self, tenant: Tenant) -> None:
        """Pré-popula o repositório com um tenant sem passar pelo save assíncrono."""
        self._store[tenant.id] = tenant
