from uuid import UUID

from modules.tenant.domain.entities.tenant_invite import TenantInvite
from shared.enums.user_role import UserRole
from shared.pagination import Page, PaginationParams, paginate_list


class FakeTenantInviteRepository:
    """
    Implementação em memória do TenantInviteRepository.
    Satisfaz o Protocol sem tocar em banco de dados.
    Usado exclusivamente em testes unitários.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, TenantInvite] = {}

    async def find_by_id(self, invite_id: UUID) -> TenantInvite | None:
        return self._store.get(invite_id)

    async def find_by_token(self, token: str) -> TenantInvite | None:
        return next(
            (i for i in self._store.values() if i.token == token),
            None,
        )

    async def find_by_email_and_tenant(
        self, email: str, tenant_id: UUID
    ) -> TenantInvite | None:
        return next(
            (
                i
                for i in self._store.values()
                if i.email.lower() == email.lower()
                and i.tenant_id == tenant_id
                and not i.is_accepted
                and not i.is_revoked
            ),
            None,
        )

    async def find_by_tenant_id_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        status: str | None = None,
        role: UserRole | None = None,
        search: str | None = None,
    ) -> Page[TenantInvite]:
        invites = [i for i in self._store.values() if i.tenant_id == tenant_id]

        if role is not None:
            invites = [i for i in invites if i.role == role]

        if search:
            s = search.lower()
            invites = [i for i in invites if s in i.email.lower()]

        if status:
            st = status.lower()
            invites = [i for i in invites if i.status.lower() == st]

        invites.sort(key=lambda i: i.created_at, reverse=True)

        return paginate_list(invites, pagination)

    async def save(self, invite: TenantInvite) -> TenantInvite:
        self._store[invite.id] = invite
        return invite

    # ─── helpers de setup ────────────────────────────────────────────────────

    def seed(self, invite: TenantInvite) -> None:
        """Pré-popula o repositório com um convite sem passar pelo save assíncrono."""
        self._store[invite.id] = invite
