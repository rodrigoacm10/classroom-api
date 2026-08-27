from uuid import UUID

from modules.tenant.domain.entities.tenant_member import TenantMember


class FakeTenantMemberRepository:
    """
    Implementação em memória do TenantMemberRepository.
    Satisfaz o Protocol sem tocar em banco de dados.
    Usado exclusivamente em testes unitários.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, TenantMember] = {}

    async def find_by_tenant_and_user(
        self,
        tenant_id: UUID,
        user_id: UUID,
    ) -> TenantMember | None:
        return next(
            (
                m
                for m in self._store.values()
                if m.tenant_id == tenant_id and m.user_id == user_id
            ),
            None,
        )

    async def find_by_user_id(self, user_id: UUID) -> list[TenantMember]:
        return [m for m in self._store.values() if m.user_id == user_id]

    async def find_by_tenant_id(self, tenant_id: UUID) -> list[TenantMember]:
        return [m for m in self._store.values() if m.tenant_id == tenant_id]

    async def save(self, member: TenantMember) -> TenantMember:
        self._store[member.id] = member
        return member

    # ─── helpers de setup ────────────────────────────────────────────────────

    def seed(self, member: TenantMember) -> None:
        """Pré-popula o repositório com um membro sem passar pelo save assíncrono."""
        self._store[member.id] = member
