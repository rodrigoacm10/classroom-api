from dataclasses import dataclass
from uuid import UUID

from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.attendance.domain.repositories.attendance_session_repository import AttendanceSessionRepository
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class ListAttendanceSessionsInput:
    tenant_id: UUID
    subject_class_id: UUID


class ListAttendanceSessionsUseCase:

    def __init__(
        self,
        session_repo: AttendanceSessionRepository,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.session_repo = session_repo
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: ListAttendanceSessionsInput) -> list[AttendanceSession]:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            data.subject_class_id, data.tenant_id
        )
        if not subject_class or getattr(subject_class, "deleted", False):
            raise ResourceNotFoundException("Turma não encontrada.")

        return await self.session_repo.list_by_class(data.subject_class_id)
