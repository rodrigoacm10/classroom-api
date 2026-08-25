from typing import Protocol
from uuid import UUID

from modules.tenant.domain.entities.tenant import Tenant
from modules.tenant.domain.entities.tenant_member import TenantMember


class TenantRepository(Protocol):

    async def find_by_id(self, tenant_id: UUID) -> Tenant | None: ...

    async def find_by_slug(self, slug: str) -> Tenant | None: ...

    async def save(self, tenant: Tenant) -> Tenant: ...


class TenantMemberRepository(Protocol):

    async def find_by_tenant_and_user(self, tenant_id: UUID, user_id: UUID) -> TenantMember | None: ...

    async def find_by_user_id(self, user_id: UUID) -> list[TenantMember]: ...

    async def find_by_tenant_id(self, tenant_id: UUID) -> list[TenantMember]: ...

    async def save(self, member: TenantMember) -> TenantMember: ...
