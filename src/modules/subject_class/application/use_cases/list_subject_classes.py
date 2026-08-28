from dataclasses import dataclass
from uuid import UUID

from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class ListSubjectClassesInput:
    tenant_id: UUID


class ListSubjectClassesUseCase:

    def __init__(
        self,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: ListSubjectClassesInput) -> list[SubjectClass]:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        return await self.subject_class_repo.list_by_tenant(data.tenant_id)
