from dataclasses import dataclass
from uuid import UUID

from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from shared.enums.enrollment_status import EnrollmentStatus
from shared.exceptions import ResourceNotFoundException


@dataclass
class ListEnrollmentsInput:
    subject_class_id: UUID
    tenant_id: UUID
    status: EnrollmentStatus | None = None
    include_deleted: bool = False


class ListEnrollmentsUseCase:

    def __init__(
        self,
        enrollment_repo: EnrollmentRepository,
        subject_class_repo: SubjectClassRepository,
    ) -> None:
        self.enrollment_repo = enrollment_repo
        self.subject_class_repo = subject_class_repo

    async def execute(self, data: ListEnrollmentsInput) -> list[Enrollment]:
        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            subject_class_id=data.subject_class_id,
            tenant_id=data.tenant_id,
        )
        if not subject_class:
            raise ResourceNotFoundException("Turma não encontrada.")

        return await self.enrollment_repo.list_by_subject_class(
            subject_class_id=data.subject_class_id,
            status=data.status,
            include_deleted=data.include_deleted,
        )
