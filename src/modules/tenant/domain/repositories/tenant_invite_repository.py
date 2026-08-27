from typing import Protocol
from uuid import UUID

from modules.tenant.domain.entities.tenant_invite import TenantInvite


class TenantInviteRepository(Protocol):

    async def find_by_token(self, token: str) -> TenantInvite | None: ...

    async def find_by_email_and_tenant(
        self, email: str, tenant_id: UUID
    ) -> TenantInvite | None: ...

    async def save(self, invite: TenantInvite) -> TenantInvite: ...
