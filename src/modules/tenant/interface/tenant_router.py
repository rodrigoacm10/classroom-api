from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.enrollment.infra.repositories.enrollment_sqlalchemy_repository import (
    EnrollmentSQLAlchemyRepository,
)
from modules.notification.infra.repositories.fcm_token_sqlalchemy_repository import (
    FCMTokenSQLAlchemyRepository,
)
from modules.tenant.application.use_cases.activate_tenant import ActivateTenantUseCase
from modules.tenant.application.use_cases.add_tenant_member import (
    AddTenantMemberInput,
    AddTenantMemberUseCase,
)
from modules.tenant.application.use_cases.create_tenant import (
    CreateTenantInput,
    CreateTenantUseCase,
)
from modules.tenant.application.use_cases.deactivate_tenant import DeactivateTenantUseCase
from modules.tenant.application.use_cases.delete_tenant import DeleteTenantUseCase
from modules.tenant.application.use_cases.get_members_metrics import (
    GetMembersMetricsInput,
    GetMembersMetricsUseCase,
)
from modules.tenant.application.use_cases.get_student import (
    GetStudentInput,
    GetStudentUseCase,
)
from modules.tenant.application.use_cases.get_students_metrics import (
    GetStudentsMetricsInput,
    GetStudentsMetricsUseCase,
)
from modules.tenant.application.use_cases.list_my_tenants import ListMyTenantsUseCase
from modules.tenant.application.use_cases.list_students import (
    ListStudentsInput,
    ListStudentsUseCase,
)
from modules.tenant.application.use_cases.list_tenant_members import (
    ListTenantMembersInput,
    ListTenantMembersUseCase,
)
from modules.tenant.application.use_cases.remove_tenant_member import (
    RemoveTenantMemberInput,
    RemoveTenantMemberUseCase,
)
from modules.tenant.application.use_cases.update_tenant_member_role import (
    UpdateTenantMemberRoleInput,
    UpdateTenantMemberRoleUseCase,
)
from modules.tenant.infra.repositories.tenant_member_sqlalchemy_repository import (
    TenantMemberSQLAlchemyRepository,
)
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import (
    TenantSQLAlchemyRepository,
)
from modules.tenant.interface.schemas.tenant_schemas import (
    AddTenantMemberRequest,
    CreateTenantRequest,
    MembersMetricsResponse,
    MyTenantResponse,
    StudentResponse,
    StudentsMetricsResponse,
    TenantMemberResponse,
    TenantResponse,
    UpdateTenantMemberRoleRequest,
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

router = APIRouter(prefix="/tenants", tags=["Tenants"])
members_router = APIRouter(prefix="/members", tags=["members"])


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: CreateTenantRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """
    Cria uma nova Tenant/Instituição.
    O usuário autenticado que criar a tenant torna-se automaticamente ADMIN dela.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = CreateTenantUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

    result = await use_case.execute(
        CreateTenantInput(
            name=body.name,
            slug=body.slug,
            owner_user_id=str(current_user.id),
        )
    )

    return TenantResponse(
        id=result.tenant.id,
        name=result.tenant.name,
        slug=result.tenant.slug,
        active=result.tenant.active,
        deleted=result.tenant.deleted,
        created_at=result.tenant.created_at,
    )


@router.get("/me", response_model=list[MyTenantResponse])
async def list_my_tenants(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MyTenantResponse]:
    """
    Lista todas as Tenants/Instituições das quais o usuário logado é membro,
    incluindo seu papel (role) em cada uma.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = ListMyTenantsUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

    items = await use_case.execute(user_id=current_user.id)

    return [
        MyTenantResponse(
            id=item.tenant.id,
            name=item.tenant.name,
            slug=item.tenant.slug,
            active=item.tenant.active,
            deleted=item.tenant.deleted,
            role=item.role,
            created_at=item.tenant.created_at,
        )
        for item in items
    ]


@router.get(
    "/{tenant_id}/members",
    response_model=PageResponse[TenantMemberResponse],
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
async def list_tenant_members(
    tenant_id: UUID,
    pagination: PaginationParams = Depends(get_pagination_params),
    role: UserRole | None = Query(None, description="Filtrar por papel (role)"),
    exclude_role: UserRole | None = Query(
        None, description="Excluir membros com este papel (ex: aluno)"
    ),
    search: str | None = Query(None, description="Busca por nome ou e-mail"),
    subject_class_id: UUID | None = Query(None, description="Filtrar por ID da turma"),
    created_after: datetime | None = Query(None, description="Membros criados a partir desta data"),
    created_before: datetime | None = Query(None, description="Membros criados até esta data"),
    include_deleted: bool = Query(False, description="Incluir membros inativos/deletados"),
    db: AsyncSession = Depends(get_db),
) -> PageResponse[TenantMemberResponse]:
    """
    Lista membros de uma Tenant/Instituição com suporte a paginação offset, total de registros e filtros avançados.
    Requer papel de ADMIN, COORDENADOR ou PROFESSOR na tenant ativa.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = ListTenantMembersUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

    page = await use_case.execute(
        ListTenantMembersInput(
            tenant_id=tenant_id,
            pagination=pagination,
            role=role,
            exclude_role=exclude_role,
            search=search,
            subject_class_id=subject_class_id,
            created_after=created_after,
            created_before=created_before,
            include_deleted=include_deleted,
        )
    )

    items = [
        TenantMemberResponse(
            id=member.id,
            tenant_id=member.tenant_id,
            user_id=member.user_id,
            name=member.name,
            email=member.email,
            role=member.role,
            created_at=member.created_at,
        )
        for member in page.items
    ]

    return PageResponse.of(page, items)


@members_router.get(
    "",
    response_model=PageResponse[TenantMemberResponse],
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
async def list_current_tenant_members(
    tenant_id: UUID = Depends(get_current_tenant_id),
    pagination: PaginationParams = Depends(get_pagination_params),
    role: UserRole | None = Query(None, description="Filtrar por papel (role)"),
    exclude_role: UserRole | None = Query(
        None, description="Excluir membros com este papel (ex: aluno)"
    ),
    search: str | None = Query(None, description="Busca por nome ou e-mail"),
    subject_class_id: UUID | None = Query(None, description="Filtrar por ID da turma"),
    created_after: datetime | None = Query(None, description="Membros criados a partir desta data"),
    created_before: datetime | None = Query(None, description="Membros criados até esta data"),
    include_deleted: bool = Query(False, description="Incluir membros inativos/deletados"),
    db: AsyncSession = Depends(get_db),
) -> PageResponse[TenantMemberResponse]:
    """
    Lista os membros institucionais do tenant ativo no token JWT (/members).
    Acessível por ADMIN, COORDENADOR e PROFESSOR.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = ListTenantMembersUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

    page = await use_case.execute(
        ListTenantMembersInput(
            tenant_id=tenant_id,
            pagination=pagination,
            role=role,
            exclude_role=exclude_role,
            search=search,
            subject_class_id=subject_class_id,
            created_after=created_after,
            created_before=created_before,
            include_deleted=include_deleted,
        )
    )

    items = [
        TenantMemberResponse(
            id=member.id,
            tenant_id=member.tenant_id,
            user_id=member.user_id,
            name=member.name,
            email=member.email,
            role=member.role,
            created_at=member.created_at,
        )
        for member in page.items
    ]

    return PageResponse.of(page, items)


@members_router.get(
    "/metrics",
    response_model=MembersMetricsResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
async def get_current_tenant_members_metrics(
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> MembersMetricsResponse:
    """
    Retorna os indicadores consolidados dos membros institucionais do tenant ativo no JWT (/members/metrics):
    total de membros (sem alunos), professores, coordenadores, administradores e turmas atribuídas.
    Acessível por ADMIN, COORDENADOR e PROFESSOR.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = GetMembersMetricsUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

    metrics = await use_case.execute(GetMembersMetricsInput(tenant_id=tenant_id))

    return MembersMetricsResponse.model_validate(metrics)


@router.get(
    "/{tenant_id}/members/metrics",
    response_model=MembersMetricsResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
async def get_tenant_members_metrics(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> MembersMetricsResponse:
    """
    Retorna os indicadores consolidados dos membros institucionais para a tenant informada no path.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = GetMembersMetricsUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

    metrics = await use_case.execute(GetMembersMetricsInput(tenant_id=tenant_id))

    return MembersMetricsResponse.model_validate(metrics)


@members_router.get(
    "/students/metrics",
    response_model=StudentsMetricsResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
async def get_students_metrics_current_tenant(
    tenant_id: UUID = Depends(get_current_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> StudentsMetricsResponse:
    """
    Retorna os indicadores consolidados dos alunos no tenant ativo:
    total de alunos, média de turmas por aluno, matrículas totais,
    taxa consolidada de frequência e alunos em atenção pedagógica (em risco).
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = GetStudentsMetricsUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

    metrics = await use_case.execute(
        GetStudentsMetricsInput(
            tenant_id=tenant_id,
            professor_user_id=auth.user.id if auth.role == UserRole.PROFESSOR else None,
        )
    )

    return StudentsMetricsResponse.model_validate(metrics)


@router.get(
    "/{tenant_id}/students/metrics",
    response_model=StudentsMetricsResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
async def get_tenant_students_metrics(
    tenant_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> StudentsMetricsResponse:
    """
    Retorna os indicadores consolidados dos alunos para a tenant informada no path.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = GetStudentsMetricsUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

    metrics = await use_case.execute(
        GetStudentsMetricsInput(
            tenant_id=tenant_id,
            professor_user_id=auth.user.id if auth.role == UserRole.PROFESSOR else None,
        )
    )

    return StudentsMetricsResponse.model_validate(metrics)


@router.get(
    "/{tenant_id}/students",
    response_model=PageResponse[StudentResponse],
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
@router.get(
    "/{tenant_id}/members/students",
    response_model=PageResponse[StudentResponse],
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
async def list_tenant_students(
    tenant_id: UUID,
    pagination: PaginationParams = Depends(get_pagination_params),
    search: str | None = Query(None, description="Busca por nome ou e-mail"),
    subject_class_id: UUID | None = Query(None, description="Filtrar por ID da turma"),
    status_filter: Literal["regular", "sem_turma"] | None = Query(
        None, alias="status", description="Filtrar por status: regular (matriculado) ou sem_turma"
    ),
    sort_by: Literal["name", "turmas_count", "created_at"] = Query(
        "name", description="Campo para ordenação (name, turmas_count, created_at)"
    ),
    order: Literal["asc", "desc"] = Query("asc", description="Direção da ordenação (asc ou desc)"),
    include_deleted: bool = Query(False, description="Incluir alunos inativos/deletados"),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> PageResponse[StudentResponse]:
    """
    Lista todos os alunos (papel ALUNO) da Tenant/Instituição informada no path,
    com contagem de turmas, taxa de presença, presenças, faltas e status pedagógico.
    Acessível por ADMIN, COORDENADOR e PROFESSOR.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = ListStudentsUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

    page = await use_case.execute(
        ListStudentsInput(
            tenant_id=tenant_id,
            pagination=pagination,
            search=search,
            subject_class_id=subject_class_id,
            professor_user_id=auth.user.id if auth.role == UserRole.PROFESSOR else None,
            status=status_filter,
            sort_by=sort_by,
            order=order,
            include_deleted=include_deleted,
        )
    )

    items = [
        StudentResponse(
            id=member.id,
            tenant_member_id=member.id,
            user_id=member.user_id,
            name=member.name,
            email=member.email,
            role=member.role,
            created_at=member.created_at,
            turmas_count=getattr(member, "turmas_count", 0),
            attendance_rate=getattr(member, "attendance_rate", 0.0),
            total_sessions=getattr(member, "total_sessions", 0),
            total_present=getattr(member, "total_present", 0),
            total_absent=getattr(member, "total_absent", 0),
            status=getattr(member, "status", "sem_turma"),
        )
        for member in page.items
    ]

    return PageResponse.of(page, items)


@members_router.get(
    "/students",
    response_model=PageResponse[StudentResponse],
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
async def list_students_current_tenant(
    tenant_id: UUID = Depends(get_current_tenant_id),
    pagination: PaginationParams = Depends(get_pagination_params),
    search: str | None = Query(None, description="Busca por nome ou e-mail"),
    subject_class_id: UUID | None = Query(None, description="Filtrar por ID da turma"),
    status_filter: Literal["regular", "sem_turma"] | None = Query(
        None, alias="status", description="Filtrar por status: regular (matriculado) ou sem_turma"
    ),
    sort_by: Literal["name", "turmas_count", "created_at"] = Query(
        "name", description="Campo para ordenação (name, turmas_count, created_at)"
    ),
    order: Literal["asc", "desc"] = Query("asc", description="Direção da ordenação (asc ou desc)"),
    include_deleted: bool = Query(False, description="Incluir alunos inativos/deletados"),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> PageResponse[StudentResponse]:
    """
    Lista todos os alunos (papel ALUNO) da instituição ativa no token JWT (/members/students),
    com contagem de turmas, taxa de presença, presenças, faltas e status pedagógico.
    Acessível por ADMIN, COORDENADOR e PROFESSOR.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = ListStudentsUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

    page = await use_case.execute(
        ListStudentsInput(
            tenant_id=tenant_id,
            pagination=pagination,
            search=search,
            subject_class_id=subject_class_id,
            professor_user_id=auth.user.id if auth.role == UserRole.PROFESSOR else None,
            status=status_filter,
            sort_by=sort_by,
            order=order,
            include_deleted=include_deleted,
        )
    )

    items = [
        StudentResponse(
            id=member.id,
            tenant_member_id=member.id,
            user_id=member.user_id,
            name=member.name,
            email=member.email,
            role=member.role,
            created_at=member.created_at,
            turmas_count=getattr(member, "turmas_count", 0),
            attendance_rate=getattr(member, "attendance_rate", 0.0),
            total_sessions=getattr(member, "total_sessions", 0),
            total_present=getattr(member, "total_present", 0),
            total_absent=getattr(member, "total_absent", 0),
            status=getattr(member, "status", "sem_turma"),
        )
        for member in page.items
    ]

    return PageResponse.of(page, items)


@members_router.get(
    "/students/{student_id}",
    response_model=StudentResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
async def get_student_detail(
    student_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> StudentResponse:
    """
    Retorna a ficha cadastral enriquecida de um aluno específico da instituição ativa no JWT.
    Acessível por ADMIN, COORDENADOR e PROFESSOR.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = GetStudentUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

    member = await use_case.execute(
        GetStudentInput(
            tenant_id=tenant_id,
            student_id=student_id,
            professor_user_id=auth.user.id if auth.role == UserRole.PROFESSOR else None,
        )
    )

    return StudentResponse(
        id=member.id,
        tenant_member_id=member.id,
        user_id=member.user_id,
        name=member.name,
        email=member.email,
        role=member.role,
        created_at=member.created_at,
        turmas_count=getattr(member, "turmas_count", 0),
        attendance_rate=getattr(member, "attendance_rate", 0.0),
        total_sessions=getattr(member, "total_sessions", 0),
        total_present=getattr(member, "total_present", 0),
        total_absent=getattr(member, "total_absent", 0),
        status=getattr(member, "status", "sem_turma"),
    )


@router.get(
    "/{tenant_id}/students/{student_id}",
    response_model=StudentResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
@router.get(
    "/{tenant_id}/members/students/{student_id}",
    response_model=StudentResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
async def get_tenant_student_detail(
    tenant_id: UUID,
    student_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> StudentResponse:
    """
    Retorna a ficha cadastral enriquecida de um aluno específico de uma instituição.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = GetStudentUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

    member = await use_case.execute(
        GetStudentInput(
            tenant_id=tenant_id,
            student_id=student_id,
            professor_user_id=auth.user.id if auth.role == UserRole.PROFESSOR else None,
        )
    )

    return StudentResponse(
        id=member.id,
        tenant_member_id=member.id,
        user_id=member.user_id,
        name=member.name,
        email=member.email,
        role=member.role,
        created_at=member.created_at,
        turmas_count=getattr(member, "turmas_count", 0),
        attendance_rate=getattr(member, "attendance_rate", 0.0),
        total_sessions=getattr(member, "total_sessions", 0),
        total_present=getattr(member, "total_present", 0),
        total_absent=getattr(member, "total_absent", 0),
        status=getattr(member, "status", "sem_turma"),
    )


@router.post(
    "/{tenant_id}/members",
    response_model=TenantMemberResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def add_tenant_member(
    tenant_id: UUID,
    body: AddTenantMemberRequest,
    db: AsyncSession = Depends(get_db),
) -> TenantMemberResponse:
    """
    Adiciona um usuário a uma Tenant específica com um perfil definido (ADMIN, PROFESSOR, ALUNO, COORDENADOR).
    Requer que a requisição seja feita por um usuário com o papel de ADMIN na tenant ativa.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = AddTenantMemberUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

    member = await use_case.execute(
        AddTenantMemberInput(
            tenant_id=tenant_id,
            user_id=body.user_id,
            role=body.role,
        )
    )

    return TenantMemberResponse(
        id=member.id,
        tenant_id=member.tenant_id,
        user_id=member.user_id,
        role=member.role,
        created_at=member.created_at,
    )


@router.patch(
    "/{tenant_id}/members/{user_id}/role",
    response_model=TenantMemberResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def update_tenant_member_role(
    tenant_id: UUID,
    user_id: UUID,
    body: UpdateTenantMemberRoleRequest,
    db: AsyncSession = Depends(get_db),
) -> TenantMemberResponse:
    """
    Altera o papel (role) de um membro ativo de uma Tenant/Instituição.
    Requer papel de ADMIN na tenant ativa.
    Não permite rebaixar o único administrador da instituição.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    enrollment_repo = EnrollmentSQLAlchemyRepository(session=db)
    use_case = UpdateTenantMemberRoleUseCase(
        tenant_repo=tenant_repo,
        member_repo=member_repo,
        enrollment_repo=enrollment_repo,
    )

    member = await use_case.execute(
        UpdateTenantMemberRoleInput(
            tenant_id=tenant_id,
            user_id_to_update=user_id,
            new_role=body.role,
        )
    )

    return TenantMemberResponse(
        id=member.id,
        tenant_id=member.tenant_id,
        user_id=member.user_id,
        role=member.role,
        created_at=member.created_at,
    )


@router.delete(
    "/{tenant_id}/members/{user_id}",
    response_model=TenantMemberResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def remove_tenant_member(
    tenant_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TenantMemberResponse:
    """
    Remove um membro de uma Tenant/Instituição (Soft Delete).
    Requer papel de ADMIN na tenant ativa.
    Não permite remover o único administrador da instituição.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    fcm_token_repo = FCMTokenSQLAlchemyRepository(session=db)
    use_case = RemoveTenantMemberUseCase(
        tenant_repo=tenant_repo,
        member_repo=member_repo,
        fcm_token_repo=fcm_token_repo,
    )

    member = await use_case.execute(
        RemoveTenantMemberInput(
            tenant_id=tenant_id,
            user_id_to_remove=user_id,
        )
    )

    return TenantMemberResponse(
        id=member.id,
        tenant_id=member.tenant_id,
        user_id=member.user_id,
        role=member.role,
        created_at=member.created_at,
    )


@router.patch(
    "/{tenant_id}/activate",
    response_model=TenantResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def activate_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """
    Ativa uma Tenant/Instituição.
    Requer papel de ADMIN na tenant ativa.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    use_case = ActivateTenantUseCase(tenant_repo=tenant_repo)
    tenant = await use_case.execute(tenant_id)
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        active=tenant.active,
        deleted=tenant.deleted,
        created_at=tenant.created_at,
    )


@router.patch(
    "/{tenant_id}/deactivate",
    response_model=TenantResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def deactivate_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """
    Desativa uma Tenant/Instituição.
    Requer papel de ADMIN na tenant ativa.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    use_case = DeactivateTenantUseCase(tenant_repo=tenant_repo)
    tenant = await use_case.execute(tenant_id)
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        active=tenant.active,
        deleted=tenant.deleted,
        created_at=tenant.created_at,
    )


@router.delete(
    "/{tenant_id}",
    response_model=TenantResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def delete_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """
    Realiza o soft delete de uma Tenant/Instituição.
    Requer papel de ADMIN na tenant ativa.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    use_case = DeleteTenantUseCase(tenant_repo=tenant_repo)
    tenant = await use_case.execute(tenant_id)
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        active=tenant.active,
        deleted=tenant.deleted,
        created_at=tenant.created_at,
    )
