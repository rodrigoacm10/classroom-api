from dataclasses import dataclass
from uuid import UUID

from modules.attendance.domain.entities.attendance_record import AttendanceRecord
from modules.attendance.domain.repositories.attendance_record_repository import AttendanceRecordRepository
from modules.attendance.domain.repositories.attendance_session_repository import AttendanceSessionRepository
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository, TenantRepository
from shared.enums.record_status import RecordStatus
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ForbiddenException, ResourceNotFoundException


@dataclass
class ReviewAttendanceRecordInput:
    tenant_id: UUID
    subject_class_id: UUID
    session_id: UUID
    record_id: UUID
    user_id: UUID
    user_role: UserRole | None
    decision: RecordStatus
    note: str | None = None


class ReviewAttendanceRecordUseCase:

    def __init__(
        self,
        record_repo: AttendanceRecordRepository,
        session_repo: AttendanceSessionRepository,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.record_repo = record_repo
        self.session_repo = session_repo
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: ReviewAttendanceRecordInput) -> AttendanceRecord:
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

        member = await self.member_repo.find_by_tenant_and_user(data.tenant_id, data.user_id)
        if not member:
            raise ForbiddenException("Usuário não é membro desta instituição.")

        is_admin = data.user_role == UserRole.ADMIN or member.role == UserRole.ADMIN
        is_professor = subject_class.professor_id == member.id

        if not (is_admin or is_professor):
            raise ForbiddenException("Apenas o professor da turma ou um administrador podem revisar registros.")

        if record.record_status == RecordStatus.REGULAR:
            raise BusinessRuleException("Apenas registros marcados como irregulares podem ser revisados.")

        if data.decision not in (RecordStatus.APPROVED, RecordStatus.REJECTED):
            raise BusinessRuleException("Decisão inválida para revisão. Escolha 'approved' ou 'rejected'.")

        if data.decision == RecordStatus.APPROVED:
            record.approve(reviewed_by=member.id, note=data.note)
        else:
            record.reject(reviewed_by=member.id, note=data.note)

        return await self.record_repo.save(record)
