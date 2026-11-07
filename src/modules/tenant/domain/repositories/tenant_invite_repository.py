from typing import Protocol
from uuid import UUID

from modules.tenant.domain.entities.tenant_invite import (
    TenantInvite,
    TenantInvitesMetrics,
)
from shared.enums.user_role import UserRole
from shared.pagination import Page, PaginationParams


class TenantInviteRepository(Protocol):
    async def find_by_id(self, invite_id: UUID) -> TenantInvite | None: ...

    async def find_by_token(self, token: str) -> TenantInvite | None: ...

    async def find_by_email_and_tenant(
        self, email: str, tenant_id: UUID
    ) -> TenantInvite | None: ...

    async def find_by_tenant_id_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        status: str | None = None,
        role: UserRole | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        order: str = "desc",
    ) -> Page[TenantInvite]: ...

    async def get_metrics(self, tenant_id: UUID, days: int = 30) -> TenantInvitesMetrics: ...

    async def save(self, invite: TenantInvite) -> TenantInvite: ...
