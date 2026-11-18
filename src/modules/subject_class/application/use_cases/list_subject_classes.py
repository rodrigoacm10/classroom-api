from dataclasses import dataclass, field
from uuid import UUID

from modules.subject_class.domain.entities.subject_class_summary import SubjectClassSummary
from modules.subject_class.domain.repositories.subject_class_repository import (
    SubjectClassRepository,
)
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from shared.enums.user_role import UserRole
from shared.exceptions import ResourceNotFoundException
from shared.pagination import Page, PaginationParams


@dataclass
class ListSubjectClassesInput:
    tenant_id: UUID
    pagination: PaginationParams = field(default_factory=PaginationParams)
    professor_id: UUID | None = None
    room_id: UUID | None = None
    search: str | None = None
    active: bool | None = None
    has_active_session: bool | None = None
    sort_by: str | None = None
    order: str | None = None
    user_id: UUID | None = None
    user_role: UserRole | None = None


class ListSubjectClassesUseCase:
    def __init__(
        self,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository | None = None,
    ) -> None:
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: ListSubjectClassesInput) -> Page[SubjectClassSummary]:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        professor_id = data.professor_id
        if data.user_role == UserRole.PROFESSOR:
            # Mesma regra das métricas: o professor só enxerga as turmas das quais é responsável.
            if data.user_id is None or self.member_repo is None:
                raise ResourceNotFoundException(
                    "Vínculo do professor não encontrado nesta instituição."
                )
            member = await self.member_repo.find_by_tenant_and_user(
                tenant_id=data.tenant_id,
                user_id=data.user_id,
            )
            if not member or member.deleted:
                raise ResourceNotFoundException(
                    "Vínculo do professor não encontrado nesta instituição."
                )
            professor_id = member.id

        return await self.subject_class_repo.find_summaries_by_tenant_paginated(
            tenant_id=data.tenant_id,
            pagination=data.pagination,
            professor_id=professor_id,
            room_id=data.room_id,
            search=data.search,
            active=data.active,
            has_active_session=data.has_active_session,
            sort_by=data.sort_by,
            order=data.order,
        )
