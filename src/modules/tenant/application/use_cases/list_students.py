from dataclasses import dataclass, field
from uuid import UUID

from modules.tenant.domain.entities.tenant_member import TenantMember
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from shared.exceptions import ResourceNotFoundException
from shared.pagination import Page, PaginationParams


@dataclass
class ListStudentsInput:
    tenant_id: UUID
    pagination: PaginationParams = field(default_factory=PaginationParams)
    search: str | None = None
    subject_class_id: UUID | None = None
    professor_user_id: UUID | None = None
    status: str | None = None
    sort_by: str = "name"
    order: str = "asc"
    include_deleted: bool = False


class ListStudentsUseCase:
    """Lista todos os alunos (papel ALUNO) da Tenant/Instituição com suporte a busca, paginação, dados do usuário e métricas de turmas/frequência."""

    def __init__(
        self,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: ListStudentsInput) -> Page[TenantMember]:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Tenant não encontrada.")

        return await self.member_repo.find_students_with_metrics_paginated(
            tenant_id=data.tenant_id,
            pagination=data.pagination,
            search=data.search,
            subject_class_id=data.subject_class_id,
            professor_user_id=data.professor_user_id,
            status=data.status,
            sort_by=data.sort_by,
            order=data.order,
            include_deleted=data.include_deleted,
        )
