from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets
from uuid import UUID

from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.attendance.domain.repositories.attendance_session_repository import AttendanceSessionRepository
from modules.room.domain.repositories.room_repository import RoomRepository
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository, TenantRepository
from shared.enums.user_role import UserRole
from shared.exceptions import (
    BusinessRuleException,
    ForbiddenException,
    ResourceAlreadyExistsException,
    ResourceNotFoundException,
)

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_day_code(length: int = 6) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


@dataclass
class OpenAttendanceSessionInput:
    tenant_id: UUID
    subject_class_id: UUID
    user_id: UUID
    user_role: UserRole | None
    room_id: UUID | None = None
    duration_minutes: int = 15


class OpenAttendanceSessionUseCase:

    def __init__(
        self,
        session_repo: AttendanceSessionRepository,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
        room_repo: RoomRepository,
    ) -> None:
        self.session_repo = session_repo
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo
        self.room_repo = room_repo

    async def execute(self, data: OpenAttendanceSessionInput) -> AttendanceSession:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            data.subject_class_id, data.tenant_id
        )
        if not subject_class or getattr(subject_class, "deleted", False):
            raise ResourceNotFoundException("Turma não encontrada.")

        # Verificar permissão
        member = await self.member_repo.find_by_tenant_and_user(data.tenant_id, data.user_id)
        if not member:
            raise ForbiddenException("Usuário não é membro desta instituição.")

        is_admin = data.user_role == UserRole.ADMIN or member.role == UserRole.ADMIN
        is_professor = subject_class.professor_id == member.id

        if not (is_admin or is_professor):
            raise ForbiddenException("Apenas o professor da turma ou um administrador podem abrir chamadas.")

        target_room_id = data.room_id or subject_class.room_id
        if not target_room_id:
            raise BusinessRuleException("A turma não tem sala cadastrada e nenhuma sala foi especificada.")

        room = await self.room_repo.find_by_id_and_tenant(target_room_id, data.tenant_id)
        if not room or room.deleted:
            raise ResourceNotFoundException("Sala especificada não foi encontrada.")

        # Verificar se já existe chamada aberta
        existing_open = await self.session_repo.find_open_session_by_class(data.subject_class_id)
        if existing_open and existing_open.is_open and not existing_open.is_expired:
            raise ResourceAlreadyExistsException("Já existe uma chamada aberta para esta turma.")

        day_code = generate_day_code(6)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=data.duration_minutes)

        session = AttendanceSession(
            subject_class_id=data.subject_class_id,
            room_id=target_room_id,
            day_code=day_code,
            expires_at=expires_at,
        )

        return await self.session_repo.save(session)
