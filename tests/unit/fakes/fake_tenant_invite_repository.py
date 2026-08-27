from uuid import UUID

from modules.tenant.domain.entities.tenant_invite import TenantInvite


class FakeTenantInviteRepository:
    """
    Implementação em memória do TenantInviteRepository.
    Satisfaz o Protocol sem tocar em banco de dados.
    Usado exclusivamente em testes unitários.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, TenantInvite] = {}

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
            ),
            None,
        )

    async def save(self, invite: TenantInvite) -> TenantInvite:
        self._store[invite.id] = invite
        return invite

    # ─── helpers de setup ────────────────────────────────────────────────────

    def seed(self, invite: TenantInvite) -> None:
        """Pré-popula o repositório com um convite sem passar pelo save assíncrono."""
        self._store[invite.id] = invite
