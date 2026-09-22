from dataclasses import dataclass
from uuid import UUID

from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class GetSubjectClassInput:
    subject_class_id: UUID
    tenant_id: UUID


class GetSubjectClassUseCase:

    def __init__(self, subject_class_repo: SubjectClassRepository) -> None:
        self.subject_class_repo = subject_class_repo

    async def execute(self, data: GetSubjectClassInput) -> SubjectClass:
        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            subject_class_id=data.subject_class_id,
            tenant_id=data.tenant_id,
        )
        if not subject_class:
            raise ResourceNotFoundException("Turma não encontrada.")
        return subject_class
