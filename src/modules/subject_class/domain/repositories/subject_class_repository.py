from typing import Protocol
from uuid import UUID

from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.entities.subject_class_metrics import SubjectClassMetrics
from modules.subject_class.domain.entities.subject_class_summary import SubjectClassSummary
from shared.pagination import Page, PaginationParams


class SubjectClassRepository(Protocol):
    async def save(self, subject_class: SubjectClass) -> SubjectClass: ...

    async def find_by_id(
        self, subject_class_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None: ...

    async def find_by_id_and_tenant(
        self, subject_class_id: UUID, tenant_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None: ...

    async def find_summary_by_id_and_tenant(
        self, subject_class_id: UUID, tenant_id: UUID, include_deleted: bool = False
    ) -> SubjectClassSummary | None: ...

    async def list_by_tenant(
        self,
        tenant_id: UUID,
        include_deleted: bool = False,
        active: bool | None = None,
    ) -> list[SubjectClass]: ...

    async def list_summaries_by_tenant(
        self,
        tenant_id: UUID,
        include_deleted: bool = False,
        professor_id: UUID | None = None,
        room_id: UUID | None = None,
        active: bool | None = None,
        days: int | None = None,
    ) -> list[SubjectClassSummary]: ...

    async def find_summaries_by_tenant_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        include_deleted: bool = False,
        professor_id: UUID | None = None,
        room_id: UUID | None = None,
        search: str | None = None,
        active: bool | None = None,
        has_active_session: bool | None = None,
        sort_by: str | None = None,
        order: str | None = None,
    ) -> Page[SubjectClassSummary]: ...

    async def get_metrics_by_tenant(
        self,
        tenant_id: UUID,
        professor_id: UUID | None = None,
        days: int | None = None,
    ) -> SubjectClassMetrics: ...

    async def delete(self, subject_class: SubjectClass) -> None: ...

