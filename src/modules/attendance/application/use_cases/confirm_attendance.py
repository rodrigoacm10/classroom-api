from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from modules.attendance.domain.entities.attendance_record import AttendanceRecord
from modules.attendance.domain.repositories.attendance_record_repository import AttendanceRecordRepository
from modules.attendance.domain.repositories.attendance_session_repository import AttendanceSessionRepository
from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository
from modules.room.domain.repositories.room_repository import RoomRepository
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository, TenantRepository
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.session_status import SessionStatus
from shared.exceptions import (
    BusinessRuleException,
    ForbiddenException,
    ResourceAlreadyExistsException,
    ResourceNotFoundException,
)


def is_mobile_user_agent(ua: str | None) -> bool:
    if not ua:
        return False
    ua_lower = ua.lower()
    return any(k in ua_lower for k in ["okhttp", "dart", "cfnetwork", "android", "iphone", "ipad", "mobile"])


@dataclass
class ConfirmAttendanceInput:
    tenant_id: UUID
    subject_class_id: UUID
    session_id: UUID
    user_id: UUID
    day_code: str
    latitude: float
    longitude: float
    gps_accuracy_meters: float | None = None
    device_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    device_info: dict | None = None


class ConfirmAttendanceUseCase:

    def __init__(
        self,
        session_repo: AttendanceSessionRepository,
        record_repo: AttendanceRecordRepository,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
        enrollment_repo: EnrollmentRepository,
        room_repo: RoomRepository,
    ) -> None:
        self.session_repo = session_repo
        self.record_repo = record_repo
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo
        self.enrollment_repo = enrollment_repo
        self.room_repo = room_repo

    async def execute(self, data: ConfirmAttendanceInput) -> AttendanceRecord:
        # 1. Tenant
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        # 2. SubjectClass
        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            data.subject_class_id, data.tenant_id
        )
        if not subject_class or getattr(subject_class, "deleted", False):
            raise ResourceNotFoundException("Turma não encontrada.")

        # 3. Session
        session = await self.session_repo.find_by_id_and_class(data.session_id, data.subject_class_id)
        if not session:
            raise ResourceNotFoundException("Sessão de chamada não encontrada.")

        # 4. Status OPEN
        if session.status == SessionStatus.CANCELLED:
            raise ResourceAlreadyExistsException("A chamada foi cancelada.")
        if session.status != SessionStatus.OPEN:
            raise ResourceAlreadyExistsException("A chamada está encerrada.")

        # 5. Expiração
        now = datetime.now(timezone.utc)
        expires_at_utc = (
            session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc)
        )
        if now >= expires_at_utc:
            raise ResourceAlreadyExistsException("A chamada está expirada.")

        # 6. Day code
        if data.day_code.strip().upper() != session.day_code.strip().upper():
            raise BusinessRuleException("Código da chamada inválido.")

        # 7. Member
        member = await self.member_repo.find_by_tenant_and_user(data.tenant_id, data.user_id)
        if not member:
            raise ForbiddenException("Usuário não é membro desta instituição.")

        # 8. Matrícula ativa
        enrollment = await self.enrollment_repo.find_by_class_and_member(
            data.subject_class_id, member.id
        )
        if not enrollment or enrollment.status != EnrollmentStatus.ACTIVE or getattr(enrollment, "deleted", False):
            raise ForbiddenException("Aluno não possui matrícula ativa nesta turma.")

        # 9. Já confirmou
        existing_record = await self.record_repo.find_by_session_and_member(data.session_id, member.id)
        if existing_record:
            raise ResourceAlreadyExistsException("Presença já confirmada nesta sessão.")

        # 10. Obter sala e raio de tolerância (sessão ou turma)
        room_id_to_use = session.room_id or subject_class.room_id
        if not room_id_to_use:
            raise BusinessRuleException("Nenhuma sala cadastrada para a chamada ou para a turma.")

        tolerance_radius = 50.0
        room = await self.room_repo.find_by_id(room_id_to_use)
        if room:
            tolerance_radius = float(room.tolerance_radius_meters)

        # 11. Calcular flags de irregularidade pré-inserção
        flags: list[str] = []

        # GPS accuracy imprecisa
        if data.gps_accuracy_meters is not None and data.gps_accuracy_meters > tolerance_radius:
            flags.append("low_gps_accuracy")

        # Perto de expirar (< 30s)
        remaining_seconds = (expires_at_utc - now).total_seconds()
        if remaining_seconds < 30:
            flags.append("confirmed_near_expiry")

        # Cliente não mobile (inclui user_agent nulo ou ausente)
        if not is_mobile_user_agent(data.user_agent):
            flags.append("non_mobile_client")

        # Dispositivo compartilhado
        if data.device_id:
            shared_rec = await self.record_repo.find_by_device_id_in_session(data.session_id, data.device_id)
            if shared_rec and shared_rec.tenant_member_id != member.id:
                flags.append("shared_device")

        return await self.record_repo.create_record(
            session_id=data.session_id,
            tenant_member_id=member.id,
            latitude=data.latitude,
            longitude=data.longitude,
            room_id=room_id_to_use,
            tolerance_radius_meters=tolerance_radius,
            gps_accuracy_meters=data.gps_accuracy_meters,
            irregularity_flags=flags,
            device_id=data.device_id,
            ip_address=data.ip_address,
            user_agent=data.user_agent,
            device_info=data.device_info,
        )
