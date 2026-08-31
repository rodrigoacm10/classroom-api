from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.attendance.application.use_cases.close_session import CloseAttendanceSessionInput, CloseAttendanceSessionUseCase
from modules.attendance.application.use_cases.confirm_attendance import ConfirmAttendanceInput, ConfirmAttendanceUseCase
from modules.attendance.application.use_cases.get_record import GetAttendanceRecordInput, GetAttendanceRecordUseCase
from modules.attendance.application.use_cases.get_session import GetAttendanceSessionInput, GetAttendanceSessionUseCase
from modules.attendance.application.use_cases.list_records import ListAttendanceRecordsInput, ListAttendanceRecordsUseCase
from modules.attendance.application.use_cases.list_sessions import ListAttendanceSessionsInput, ListAttendanceSessionsUseCase
from modules.attendance.application.use_cases.open_session import OpenAttendanceSessionInput, OpenAttendanceSessionUseCase
from modules.attendance.application.use_cases.review_record import ReviewAttendanceRecordInput, ReviewAttendanceRecordUseCase
from modules.attendance.infra.repositories.record_sqlalchemy_repository import RecordSQLAlchemyRepository
from modules.attendance.infra.repositories.session_sqlalchemy_repository import SessionSQLAlchemyRepository
from modules.attendance.interface.schemas.record_schemas import (
    AttendanceRecordResponse,
    ConfirmAttendanceRequest,
    ReviewAttendanceRecordRequest,
)
from modules.attendance.interface.schemas.session_schemas import (
    AttendanceSessionResponse,
    CreateAttendanceSessionRequest,
)
from modules.enrollment.infra.repositories.enrollment_sqlalchemy_repository import EnrollmentSQLAlchemyRepository
from modules.room.infra.repositories.room_sqlalchemy_repository import RoomSQLAlchemyRepository
from modules.subject_class.infra.repositories.subject_class_sqlalchemy_repository import SubjectClassSQLAlchemyRepository
from modules.tenant.infra.repositories.tenant_member_sqlalchemy_repository import TenantMemberSQLAlchemyRepository
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import TenantSQLAlchemyRepository
from security.dependencies.current_user import AuthContext, get_auth_context
from security.dependencies.require_role import require_role
from shared.enums.record_status import RecordStatus
from shared.enums.user_role import UserRole

router = APIRouter(
    prefix="/tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions",
    tags=["attendance"],
)


@router.post(
    "",
    response_model=AttendanceSessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def open_attendance_session(
    tenant_id: UUID,
    subject_class_id: UUID,
    body: CreateAttendanceSessionRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> AttendanceSessionResponse:
    """Abre uma nova sessão de chamada para a turma com código do dia e janela de expiração."""
    session_repo = SessionSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    room_repo = RoomSQLAlchemyRepository(session=db)

    use_case = OpenAttendanceSessionUseCase(
        session_repo=session_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        member_repo=member_repo,
        room_repo=room_repo,
    )

    session = await use_case.execute(
        OpenAttendanceSessionInput(
            tenant_id=tenant_id,
            subject_class_id=subject_class_id,
            user_id=auth.user.id,
            user_role=auth.role,
            room_id=body.room_id,
            duration_minutes=body.duration_minutes,
        )
    )
    return AttendanceSessionResponse.model_validate(session)


@router.get("", response_model=list[AttendanceSessionResponse])
async def list_attendance_sessions(
    tenant_id: UUID,
    subject_class_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[AttendanceSessionResponse]:
    """Lista todas as sessões de chamada de uma turma."""
    session_repo = SessionSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)

    use_case = ListAttendanceSessionsUseCase(
        session_repo=session_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
    )

    sessions = await use_case.execute(
        ListAttendanceSessionsInput(
            tenant_id=tenant_id,
            subject_class_id=subject_class_id,
        )
    )
    return [AttendanceSessionResponse.model_validate(s) for s in sessions]


@router.get("/{session_id}", response_model=AttendanceSessionResponse)
async def get_attendance_session(
    tenant_id: UUID,
    subject_class_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AttendanceSessionResponse:
    """Retorna os detalhes de uma sessão de chamada específica."""
    session_repo = SessionSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)

    use_case = GetAttendanceSessionUseCase(
        session_repo=session_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
    )

    session = await use_case.execute(
        GetAttendanceSessionInput(
            tenant_id=tenant_id,
            subject_class_id=subject_class_id,
            session_id=session_id,
        )
    )
    return AttendanceSessionResponse.model_validate(session)


@router.patch(
    "/{session_id}/close",
    response_model=AttendanceSessionResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def close_attendance_session(
    tenant_id: UUID,
    subject_class_id: UUID,
    session_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> AttendanceSessionResponse:
    """Encerra manualmente uma chamada em aberto."""
    session_repo = SessionSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)

    use_case = CloseAttendanceSessionUseCase(
        session_repo=session_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        member_repo=member_repo,
    )

    session = await use_case.execute(
        CloseAttendanceSessionInput(
            tenant_id=tenant_id,
            subject_class_id=subject_class_id,
            session_id=session_id,
            user_id=auth.user.id,
            user_role=auth.role,
        )
    )
    return AttendanceSessionResponse.model_validate(session)


@router.post(
    "/{session_id}/confirm",
    response_model=AttendanceRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_attendance(
    tenant_id: UUID,
    subject_class_id: UUID,
    session_id: UUID,
    body: ConfirmAttendanceRequest,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> AttendanceRecordResponse:
    """Confirma presença de um aluno matriculado validando código e geolocalização."""
    session_repo = SessionSQLAlchemyRepository(session=db)
    record_repo = RecordSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    enrollment_repo = EnrollmentSQLAlchemyRepository(session=db)
    room_repo = RoomSQLAlchemyRepository(session=db)

    use_case = ConfirmAttendanceUseCase(
        session_repo=session_repo,
        record_repo=record_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        member_repo=member_repo,
        enrollment_repo=enrollment_repo,
        room_repo=room_repo,
    )

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    record = await use_case.execute(
        ConfirmAttendanceInput(
            tenant_id=tenant_id,
            subject_class_id=subject_class_id,
            session_id=session_id,
            user_id=auth.user.id,
            day_code=body.day_code,
            latitude=body.latitude,
            longitude=body.longitude,
            gps_accuracy_meters=body.gps_accuracy_meters,
            device_id=body.device_id,
            ip_address=ip_address,
            user_agent=user_agent,
            device_info=body.device_info,
        )
    )
    return AttendanceRecordResponse.model_validate(record)


@router.get(
    "/{session_id}/records",
    response_model=list[AttendanceRecordResponse],
)
async def list_attendance_records(
    tenant_id: UUID,
    subject_class_id: UUID,
    session_id: UUID,
    record_status: RecordStatus | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[AttendanceRecordResponse]:
    """Lista todos os registros de presença de uma sessão, com suporte a filtro por status de auditoria."""
    record_repo = RecordSQLAlchemyRepository(session=db)
    session_repo = SessionSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)

    use_case = ListAttendanceRecordsUseCase(
        record_repo=record_repo,
        session_repo=session_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
    )

    records = await use_case.execute(
        ListAttendanceRecordsInput(
            tenant_id=tenant_id,
            subject_class_id=subject_class_id,
            session_id=session_id,
            record_status=record_status,
        )
    )
    return [AttendanceRecordResponse.model_validate(r) for r in records]


@router.get(
    "/{session_id}/records/{record_id}",
    response_model=AttendanceRecordResponse,
)
async def get_attendance_record(
    tenant_id: UUID,
    subject_class_id: UUID,
    session_id: UUID,
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AttendanceRecordResponse:
    """Retorna os detalhes de um registro de presença específico."""
    record_repo = RecordSQLAlchemyRepository(session=db)
    session_repo = SessionSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)

    use_case = GetAttendanceRecordUseCase(
        record_repo=record_repo,
        session_repo=session_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
    )

    record = await use_case.execute(
        GetAttendanceRecordInput(
            tenant_id=tenant_id,
            subject_class_id=subject_class_id,
            session_id=session_id,
            record_id=record_id,
        )
    )
    return AttendanceRecordResponse.model_validate(record)


@router.patch(
    "/{session_id}/records/{record_id}/review",
    response_model=AttendanceRecordResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def review_attendance_record(
    tenant_id: UUID,
    subject_class_id: UUID,
    session_id: UUID,
    record_id: UUID,
    body: ReviewAttendanceRecordRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> AttendanceRecordResponse:
    """Permite ao professor ou admin aprovar ou rejeitar um registro de presença irregular."""
    record_repo = RecordSQLAlchemyRepository(session=db)
    session_repo = SessionSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)

    use_case = ReviewAttendanceRecordUseCase(
        record_repo=record_repo,
        session_repo=session_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        member_repo=member_repo,
    )

    record = await use_case.execute(
        ReviewAttendanceRecordInput(
            tenant_id=tenant_id,
            subject_class_id=subject_class_id,
            session_id=session_id,
            record_id=record_id,
            user_id=auth.user.id,
            user_role=auth.role,
            decision=body.decision,
            note=body.note,
        )
    )
    return AttendanceRecordResponse.model_validate(record)
