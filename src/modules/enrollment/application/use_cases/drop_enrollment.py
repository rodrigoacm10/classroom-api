from dataclasses import dataclass
from uuid import UUID

from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository
from shared.enums.enrollment_status import EnrollmentStatus
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class DropEnrollmentInput:
    enrollment_id: UUID
    subject_class_id: UUID


class DropEnrollmentUseCase:
    """Cancela uma matrícula por evento de negócio legítimo.
    Altera o status para DROPPED. O registro é PRESERVADO no histórico.
    """

    def __init__(self, enrollment_repo: EnrollmentRepository) -> None:
        self.enrollment_repo = enrollment_repo

    async def execute(self, data: DropEnrollmentInput) -> None:
        enrollment = await self.enrollment_repo.find_by_id(
            data.enrollment_id, include_deleted=False
        )
        if not enrollment or enrollment.subject_class_id != data.subject_class_id:
            raise ResourceNotFoundException("Matrícula não encontrada.")

        if enrollment.status == EnrollmentStatus.DROPPED:
            raise BusinessRuleException("Matrícula já está cancelada.")

        enrollment.status = EnrollmentStatus.DROPPED
        await self.enrollment_repo.save(enrollment)
