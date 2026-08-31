from dataclasses import dataclass
from uuid import UUID

from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class DeleteEnrollmentInput:
    enrollment_id: UUID
    subject_class_id: UUID


class DeleteEnrollmentUseCase:
    """Remove uma matrícula por correção de erro administrativo.
    Realiza soft delete (deleted=True). O registro some de visualizações normais.
    Exclusivo para ADMIN.
    """

    def __init__(self, enrollment_repo: EnrollmentRepository) -> None:
        self.enrollment_repo = enrollment_repo

    async def execute(self, data: DeleteEnrollmentInput) -> None:
        enrollment = await self.enrollment_repo.find_by_id(
            data.enrollment_id, include_deleted=False
        )
        if not enrollment or enrollment.subject_class_id != data.subject_class_id:
            raise ResourceNotFoundException("Matrícula não encontrada.")

        enrollment.deleted = True
        await self.enrollment_repo.save(enrollment)
