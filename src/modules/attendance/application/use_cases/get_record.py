from dataclasses import dataclass
from uuid import UUID

from modules.attendance.domain.entities.attendance_record import AttendanceRecord
from modules.attendance.domain.repositories.attendance_record_repository import AttendanceRecordRepository
from modules.attendance.domain.repositories.attendance_session_repository import AttendanceSessionRepository
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class GetAttendanceRecordInput:
    tenant_id: UUID
    subject_class_id: UUID
    session_id: UUID
    record_id: UUID


class GetAttendanceRecordUseCase:

    def __init__(
        self,
        record_repo: AttendanceRecordRepository,
        session_repo: AttendanceSessionRepository,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.record_repo = record_repo
        self.session_repo = session_repo
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: GetAttendanceRecordInput) -> AttendanceRecord:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            data.subject_class_id, data.tenant_id
        )
        if not subject_class or getattr(subject_class, "deleted", False):
            raise ResourceNotFoundException("Turma não encontrada.")

        session = await self.session_repo.find_by_id_and_class(data.session_id, data.subject_class_id)
        if not session:
            raise ResourceNotFoundException("Sessão de chamada não encontrada.")

        record = await self.record_repo.find_by_id_and_session(data.record_id, data.session_id)
        if not record:
            raise ResourceNotFoundException("Registro de presença não encontrado.")

        return record
