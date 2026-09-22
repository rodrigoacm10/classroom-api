from datetime import datetime
from uuid import UUID

from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from shared.pagination import Page, PaginationParams, paginate_list


class FakeTenantMemberRepository:
    """
    Implementação em memória do TenantMemberRepository.
    Satisfaz o Protocol sem tocar em banco de dados.
    Usado exclusivamente em testes unitários.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, TenantMember] = {}

    async def find_by_id(
        self, member_id: UUID, include_deleted: bool = False
    ) -> TenantMember | None:
        m = self._store.get(member_id)
        if m and (include_deleted or not m.deleted):
            return m
        return None

    async def find_by_tenant_and_user(
        self,
        tenant_id: UUID,
        user_id: UUID,
        include_deleted: bool = False,
    ) -> TenantMember | None:
        return next(
            (
                m
                for m in self._store.values()
                if m.tenant_id == tenant_id
                and m.user_id == user_id
                and (include_deleted or not m.deleted)
            ),
            None,
        )

    async def find_by_user_id(
        self, user_id: UUID, include_deleted: bool = False
    ) -> list[TenantMember]:
        return [
            m
            for m in self._store.values()
            if m.user_id == user_id and (include_deleted or not m.deleted)
        ]

    async def find_by_tenant_id_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        role: UserRole | None = None,
        search: str | None = None,
        subject_class_id: UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        include_deleted: bool = False,
    ) -> Page[TenantMember]:
        results = []
        for m in self._store.values():
            if m.tenant_id != tenant_id:
                continue
            if not include_deleted and m.deleted:
                continue
            if role is not None and m.role != role:
                continue
            if created_after is not None and m.created_at < created_after:
                continue
            if created_before is not None and m.created_at > created_before:
                continue
            if subject_class_id is not None and getattr(m, "_subject_class_id", None) != subject_class_id:
                continue
            if search is not None:
                search_lower = search.lower()
                user_name = getattr(m, "_user_name", "").lower()
                user_email = getattr(m, "_user_email", "").lower()
                if search_lower not in user_name and search_lower not in user_email:
                    continue
            results.append(m)
        return paginate_list(results, pagination)

    async def count_active_admins(self, tenant_id: UUID) -> int:
        return len(
            [
                m
                for m in self._store.values()
                if m.tenant_id == tenant_id
                and m.role == UserRole.ADMIN
                and not m.deleted
            ]
        )

    async def save(self, member: TenantMember) -> TenantMember:
        self._store[member.id] = member
        return member

    # ─── helpers de setup ────────────────────────────────────────────────────

    def seed(self, member: TenantMember) -> None:
        """Pré-popula o repositório com um membro sem passar pelo save assíncrono."""
        self._store[member.id] = member
