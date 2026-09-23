from dataclasses import dataclass, field
from uuid import UUID

from modules.subject_class.domain.entities.subject_class_summary import SubjectClassSummary
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException
from shared.pagination import Page, PaginationParams


@dataclass
class ListSubjectClassesInput:
    tenant_id: UUID
    pagination: PaginationParams = field(default_factory=PaginationParams)
    professor_id: UUID | None = None
    room_id: UUID | None = None
    search: str | None = None


class ListSubjectClassesUseCase:

    def __init__(
        self,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: ListSubjectClassesInput) -> Page[SubjectClassSummary]:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        return await self.subject_class_repo.find_summaries_by_tenant_paginated(
            tenant_id=data.tenant_id,
            pagination=data.pagination,
            professor_id=data.professor_id,
            room_id=data.room_id,
            search=data.search,
        )
