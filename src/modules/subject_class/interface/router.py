from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.room.infra.repositories.room_sqlalchemy_repository import RoomSQLAlchemyRepository
from modules.subject_class.application.use_cases.create_subject_class import (
    CreateSubjectClassInput,
    CreateSubjectClassUseCase,
)
from modules.subject_class.application.use_cases.delete_subject_class import (
    DeleteSubjectClassInput,
    DeleteSubjectClassUseCase,
)
from modules.subject_class.application.use_cases.get_subject_class import (
    GetSubjectClassInput,
    GetSubjectClassUseCase,
)
from modules.subject_class.application.use_cases.get_subject_class_metrics import (
    GetSubjectClassMetricsInput,
    GetSubjectClassMetricsUseCase,
)
from modules.subject_class.application.use_cases.list_subject_classes import (
    ListSubjectClassesInput,
    ListSubjectClassesUseCase,
)
from modules.subject_class.application.use_cases.update_subject_class import (
    UpdateSubjectClassInput,
    UpdateSubjectClassUseCase,
)
from modules.subject_class.infra.repositories.subject_class_sqlalchemy_repository import (
    SubjectClassSQLAlchemyRepository,
)
from modules.subject_class.interface.schemas.subject_class_schemas import (
    CreateSubjectClassRequest,
    SubjectClassListItemResponse,
    SubjectClassMetricsResponse,
    SubjectClassResponse,
    UpdateSubjectClassRequest,
)
from modules.tenant.infra.repositories.tenant_member_sqlalchemy_repository import (
    TenantMemberSQLAlchemyRepository,
)
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import (
    TenantSQLAlchemyRepository,
)
from modules.user.domain.entities.user import User
from security.dependencies.current_user import (
    AuthContext,
    get_auth_context,
    get_current_tenant_id,
    get_current_user,
)
from security.dependencies.require_role import require_role
from shared.enums.user_role import UserRole
from shared.pagination import PageResponse, PaginationParams, get_pagination_params

router = APIRouter(prefix="/subject-classes", tags=["subject-classes"])


@router.post(
    "",
    response_model=SubjectClassResponse,
    status_code=201,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def create_subject_class(
    body: CreateSubjectClassRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubjectClassResponse:
    """Cadastra uma nova turma de disciplina para a Tenant. Requer papel ADMIN ou PROFESSOR."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    room_repo = RoomSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = CreateSubjectClassUseCase(
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        room_repo=room_repo,
        member_repo=member_repo,
    )
    subject_class = await use_case.execute(
        CreateSubjectClassInput(
            tenant_id=tenant_id,
            professor_id=current_user.id,
            room_id=body.room_id,
            name=body.name,
            discipline_name=body.discipline_name,
        )
    )
    return SubjectClassResponse.model_validate(subject_class)


@router.get("", response_model=PageResponse[SubjectClassListItemResponse])
async def list_subject_classes(
    tenant_id: UUID = Depends(get_current_tenant_id),
    pagination: PaginationParams = Depends(get_pagination_params),
    professor_id: UUID | None = Query(None, description="Filtrar por ID do professor responsável"),
    room_id: UUID | None = Query(None, description="Filtrar por ID da sala vinculada"),
    search: str | None = Query(None, description="Busca por nome da turma, disciplina, professor ou sala"),
    active: bool | None = Query(None, description="Filtrar por status ativo/inativo"),
    has_active_session: bool | None = Query(None, description="Filtrar turmas com chamada aberta agora"),
    sort_by: str | None = Query(None, description="Campo de ordenação (name, attendance_rate, student_count, created_at)"),
    order: str | None = Query("asc", description="Direção da ordenação (asc ou desc)"),
    db: AsyncSession = Depends(get_db),
) -> PageResponse[SubjectClassListItemResponse]:
    """Lista turmas da Tenant com filtros, busca ampla, ordenação e taxa de presença."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    use_case = ListSubjectClassesUseCase(
        subject_class_repo=subject_class_repo, tenant_repo=tenant_repo
    )

    page = await use_case.execute(
        ListSubjectClassesInput(
            tenant_id=tenant_id,
            pagination=pagination,
            professor_id=professor_id,
            room_id=room_id,
            search=search,
            active=active,
            has_active_session=has_active_session,
            sort_by=sort_by,
            order=order,
        )
    )
    items = [SubjectClassListItemResponse.model_validate(c) for c in page.items]
    return PageResponse.of(page, items)


@router.get(
    "/metrics",
    response_model=SubjectClassMetricsResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
async def get_subject_class_metrics(
    days: int | None = Query(30, ge=1, le=365, description="Janela de dias para taxa de presença média (padrão: 30)"),
    professor_id: UUID | None = Query(None, description="Filtrar métricas por professor específico (apenas ADMIN/COORDENADOR)"),
    tenant_id: UUID = Depends(get_current_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> SubjectClassMetricsResponse:
    """Retorna métricas consolidadas das turmas (total, ativas, alunos matriculados, frequência média, em risco e ao vivo)."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)

    use_case = GetSubjectClassMetricsUseCase(
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        member_repo=member_repo,
    )

    metrics = await use_case.execute(
        GetSubjectClassMetricsInput(
            tenant_id=tenant_id,
            user_id=auth.user.id,
            user_role=auth.role,
            professor_id=professor_id,
            days=days,
        )
    )

    return SubjectClassMetricsResponse.model_validate(metrics)


@router.get("/{subject_class_id}", response_model=SubjectClassListItemResponse)
async def get_subject_class(
    subject_class_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> SubjectClassListItemResponse:
    """Retorna os detalhes enriquecidos de uma turma. Retorna 404 se deletada ou inexistente."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    use_case = GetSubjectClassUseCase(subject_class_repo=subject_class_repo)

    subject_class = await use_case.execute(
        GetSubjectClassInput(subject_class_id=subject_class_id, tenant_id=tenant_id)
    )
    return SubjectClassListItemResponse.model_validate(subject_class)


@router.patch(
    "/{subject_class_id}",
    response_model=SubjectClassResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def update_subject_class(
    subject_class_id: UUID,
    body: UpdateSubjectClassRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> SubjectClassResponse:
    """Atualiza parcialmente os dados de uma turma. Retorna 404 se deletada."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    room_repo = RoomSQLAlchemyRepository(session=db)
    use_case = UpdateSubjectClassUseCase(subject_class_repo=subject_class_repo, room_repo=room_repo)

    subject_class = await use_case.execute(
        UpdateSubjectClassInput(
            subject_class_id=subject_class_id,
            tenant_id=tenant_id,
            name=body.name,
            discipline_name=body.discipline_name,
            room_id=body.room_id,
            active=body.active,
        )
    )
    return SubjectClassResponse.model_validate(subject_class)


@router.delete(
    "/{subject_class_id}",
    status_code=204,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def delete_subject_class(
    subject_class_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete de uma turma. Requer papel ADMIN. Retorna 404 se já deletada."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    use_case = DeleteSubjectClassUseCase(subject_class_repo=subject_class_repo)

    await use_case.execute(
        DeleteSubjectClassInput(subject_class_id=subject_class_id, tenant_id=tenant_id)
    )
