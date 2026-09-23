from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, File, Form, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from infra.storage.r2_storage_service import R2StorageService
from modules.attendance.application.use_cases.cancel_session import CancelAttendanceSessionInput, CancelAttendanceSessionUseCase
from modules.attendance.application.use_cases.close_session import CloseAttendanceSessionInput, CloseAttendanceSessionUseCase
from modules.attendance.application.use_cases.confirm_attendance import ConfirmAttendanceInput, ConfirmAttendanceUseCase
from modules.attendance.application.use_cases.get_record import GetAttendanceRecordInput, GetAttendanceRecordUseCase
from modules.attendance.application.use_cases.get_session import GetAttendanceSessionInput, GetAttendanceSessionUseCase
from modules.attendance.application.use_cases.list_records import ListAttendanceRecordsInput, ListAttendanceRecordsUseCase
from modules.attendance.application.use_cases.list_session_roster import ListSessionRosterInput, ListSessionRosterUseCase
from modules.attendance.application.use_cases.list_sessions import ListAttendanceSessionsInput, ListAttendanceSessionsUseCase
from modules.attendance.application.use_cases.open_session import OpenAttendanceSessionInput, OpenAttendanceSessionUseCase
from modules.attendance.application.use_cases.review_record import ReviewAttendanceRecordInput, ReviewAttendanceRecordUseCase
from modules.attendance.infra.repositories.record_sqlalchemy_repository import RecordSQLAlchemyRepository
from modules.attendance.infra.repositories.session_sqlalchemy_repository import SessionSQLAlchemyRepository
from modules.attendance.interface.schemas.record_schemas import (
    AttendanceRecordResponse,
    ReviewAttendanceRecordRequest,
    SessionRosterItemResponse,
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
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.events.event_dispatcher import EventDispatcher
from shared.pagination import PageResponse, PaginationParams, get_pagination_params


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
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> AttendanceSessionResponse:
    """Abre uma nova sessão de chamada para a turma com código do dia e janela de expiração."""
    session_repo = SessionSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    room_repo = RoomSQLAlchemyRepository(session=db)
    event_dispatcher: EventDispatcher = request.app.state.event_dispatcher

    use_case = OpenAttendanceSessionUseCase(
        session_repo=session_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        member_repo=member_repo,
        room_repo=room_repo,
        event_dispatcher=event_dispatcher,
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


@router.get("", response_model=PageResponse[AttendanceSessionResponse])
async def list_attendance_sessions(
    tenant_id: UUID,
    subject_class_id: UUID,
    pagination: PaginationParams = Depends(get_pagination_params),
    session_status: SessionStatus | None = Query(
        None,
        alias="status",
        description="Filtrar por status da chamada (open, closed, cancelled)",
    ),
    opened_after: datetime | None = Query(
        None,
        description="Filtrar por chamadas abertas a partir desta data (ISO-8601)",
    ),
    opened_before: datetime | None = Query(
        None,
        description="Filtrar por chamadas abertas até esta data (ISO-8601)",
    ),
    db: AsyncSession = Depends(get_db),
) -> PageResponse[AttendanceSessionResponse]:
    """Lista sessões de chamada de uma turma com paginação offset e filtro por período e status."""
    session_repo = SessionSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)

    use_case = ListAttendanceSessionsUseCase(
        session_repo=session_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
    )

    page = await use_case.execute(
        ListAttendanceSessionsInput(
            tenant_id=tenant_id,
            subject_class_id=subject_class_id,
            pagination=pagination,
            status=session_status,
            opened_after=opened_after,
            opened_before=opened_before,
        )
    )
    items = [AttendanceSessionResponse.model_validate(s) for s in page.items]
    return PageResponse.of(page, items)


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
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> AttendanceSessionResponse:
    """Encerra manualmente uma chamada em aberto."""
    session_repo = SessionSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    event_dispatcher: EventDispatcher = request.app.state.event_dispatcher

    use_case = CloseAttendanceSessionUseCase(
        session_repo=session_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        member_repo=member_repo,
        event_dispatcher=event_dispatcher,
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


@router.patch(
    "/{session_id}/cancel",
    response_model=AttendanceSessionResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def cancel_attendance_session(
    tenant_id: UUID,
    subject_class_id: UUID,
    session_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> AttendanceSessionResponse:
    """Cancela manualmente uma chamada em aberto."""
    session_repo = SessionSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)

    use_case = CancelAttendanceSessionUseCase(
        session_repo=session_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        member_repo=member_repo,
    )

    session = await use_case.execute(
        CancelAttendanceSessionInput(
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
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
    day_code: str = Form(..., min_length=1, max_length=10, description="Código de 6 caracteres alfanuméricos exibido pelo professor"),
    latitude: float = Form(..., ge=-90.0, le=90.0, description="Latitude do dispositivo (WGS84)"),
    longitude: float = Form(..., ge=-180.0, le=180.0, description="Longitude do dispositivo (WGS84)"),
    gps_accuracy_meters: float | None = Form(default=None, ge=0.0, description="Precisão do GPS em metros relatada pelo dispositivo"),
    device_id: str | None = Form(default=None, max_length=64, description="Identificador único do dispositivo"),
    device_info: str | None = Form(default=None, description="Metadados do dispositivo em formato JSON (string, processado pelo use case)"),
    photo: UploadFile | None = File(default=None, description="Foto de evidência opcional (JPEG, PNG ou WebP, até 5MB)"),
) -> AttendanceRecordResponse:
    """Confirma presença de um aluno matriculado validando código e geolocalização, com foto de evidência opcional."""

    photo_bytes: bytes | None = None
    photo_content_type: str | None = None
    if photo is not None:
        photo_bytes = await photo.read()
        photo_content_type = photo.content_type

    session_repo = SessionSQLAlchemyRepository(session=db)
    record_repo = RecordSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    enrollment_repo = EnrollmentSQLAlchemyRepository(session=db)
    room_repo = RoomSQLAlchemyRepository(session=db)
    storage_service = R2StorageService()

    use_case = ConfirmAttendanceUseCase(
        session_repo=session_repo,
        record_repo=record_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        member_repo=member_repo,
        enrollment_repo=enrollment_repo,
        room_repo=room_repo,
        storage_service=storage_service,
    )

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    record = await use_case.execute(
        ConfirmAttendanceInput(
            tenant_id=tenant_id,
            subject_class_id=subject_class_id,
            session_id=session_id,
            user_id=auth.user.id,
            day_code=day_code,
            latitude=latitude,
            longitude=longitude,
            gps_accuracy_meters=gps_accuracy_meters,
            device_id=device_id,
            ip_address=ip_address,
            user_agent=user_agent,
            device_info=device_info,
            evidence_photo_bytes=photo_bytes,
            evidence_photo_content_type=photo_content_type,
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
    "/{session_id}/roster",
    response_model=list[SessionRosterItemResponse],
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def list_session_roster(
    tenant_id: UUID,
    subject_class_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[SessionRosterItemResponse]:
    """Lista todos os alunos ativos da turma na chamada, com horário, distância e status quando houver presença."""
    record_repo = RecordSQLAlchemyRepository(session=db)
    session_repo = SessionSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)

    use_case = ListSessionRosterUseCase(
        record_repo=record_repo,
        session_repo=session_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
    )
    roster = await use_case.execute(
        ListSessionRosterInput(
            tenant_id=tenant_id,
            subject_class_id=subject_class_id,
            session_id=session_id,
        )
    )
    return [SessionRosterItemResponse.model_validate(item) for item in roster]


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
