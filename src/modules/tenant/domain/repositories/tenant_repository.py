from datetime import datetime
from typing import Protocol
from uuid import UUID

from modules.tenant.domain.entities.students_metrics import StudentsMetrics
from modules.tenant.domain.entities.tenant import Tenant
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from shared.pagination import Page, PaginationParams


class TenantRepository(Protocol):
    async def find_by_id(self, tenant_id: UUID, include_deleted: bool = False) -> Tenant | None: ...

    async def find_by_slug(self, slug: str, include_deleted: bool = False) -> Tenant | None: ...

    async def save(self, tenant: Tenant) -> Tenant: ...


class TenantMemberRepository(Protocol):
    async def find_by_id(
        self, member_id: UUID, include_deleted: bool = False
    ) -> TenantMember | None: ...

    async def find_by_tenant_and_user(
        self, tenant_id: UUID, user_id: UUID, include_deleted: bool = False
    ) -> TenantMember | None: ...

    async def find_by_user_id(
        self, user_id: UUID, include_deleted: bool = False
    ) -> list[TenantMember]: ...

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
    ) -> Page[TenantMember]: ...

    async def find_students_with_metrics_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        search: str | None = None,
        subject_class_id: UUID | None = None,
        professor_user_id: UUID | None = None,
        status: str | None = None,
        sort_by: str = "name",
        order: str = "asc",
        include_deleted: bool = False,
    ) -> Page[TenantMember]: ...

    async def find_student_with_metrics_by_id(
        self,
        tenant_id: UUID,
        student_id: UUID,
        professor_user_id: UUID | None = None,
        include_deleted: bool = False,
    ) -> TenantMember | None: ...

    async def get_students_metrics(
        self,
        tenant_id: UUID,
        professor_user_id: UUID | None = None,
    ) -> StudentsMetrics: ...

    async def count_active_admins(self, tenant_id: UUID) -> int: ...

    async def save(self, member: TenantMember) -> TenantMember: ...
