from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.enrollment.infra.repositories.enrollment_sqlalchemy_repository import (
    EnrollmentSQLAlchemyRepository,
)
from modules.tenant.application.use_cases.accept_invite import AcceptInviteUseCase
from modules.tenant.application.use_cases.get_invite import GetInviteUseCase
from modules.tenant.application.use_cases.get_tenant_invites_metrics import (
    GetTenantInvitesMetricsInput,
    GetTenantInvitesMetricsUseCase,
)
from modules.tenant.application.use_cases.list_tenant_invites import (
    ListTenantInvitesInput,
    ListTenantInvitesUseCase,
)
from modules.tenant.application.use_cases.resend_invite import (
    ResendInviteInput,
    ResendInviteUseCase,
)
from modules.tenant.application.use_cases.revoke_invite import (
    RevokeInviteInput,
    RevokeInviteUseCase,
)
from modules.tenant.application.use_cases.send_invite import (
    SendInviteInput,
    SendInviteUseCase,
)
from modules.tenant.domain.entities.tenant_invite import TenantInvite
from modules.tenant.infra.repositories.tenant_invite_sqlalchemy_repository import (
    TenantInviteSQLAlchemyRepository,
)
from modules.tenant.infra.repositories.tenant_member_sqlalchemy_repository import (
    TenantMemberSQLAlchemyRepository,
)
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import (
    TenantSQLAlchemyRepository,
)
from modules.tenant.interface.schemas.tenant_schemas import (
    InviteStatusResponse,
    SendInviteRequest,
    TenantInvitesMetricsResponse,
    TenantMemberResponse,
)
from modules.user.domain.entities.user import User
from modules.user.infra.repositories.user_sqlalchemy_repository import UserSQLAlchemyRepository
from security.dependencies.current_user import get_current_tenant_id, get_current_user
from security.dependencies.require_role import require_role
from shared.enums.user_role import UserRole
from shared.pagination import PageResponse, PaginationParams, get_pagination_params

tenant_invites_router = APIRouter(prefix="/tenants", tags=["Invites"])
invites_router = APIRouter(prefix="/invites", tags=["Invites"])


def _to_invite_response(invite: TenantInvite, tenant_name: str) -> InviteStatusResponse:
    """Mapeia a entidade de domínio TenantInvite para o schema HTTP InviteStatusResponse."""
    return InviteStatusResponse(
        id=invite.id,
        tenant_id=invite.tenant_id,
        tenant_name=tenant_name,
        email=invite.email,
        role=invite.role,
        token=invite.token,
        status=invite.status,
        subject_class_ids=invite.subject_class_ids,
        subject_class_names=invite.subject_class_names,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
        accepted_at=invite.accepted_at,
        revoked_at=invite.revoked_at,
        invited_by_name=invite.invited_by_name,
    )


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS SOB /tenants/{tenant_id}/invites
# ══════════════════════════════════════════════════════════════════════════════


@tenant_invites_router.post(
    "/{tenant_id}/invites",
    response_model=InviteStatusResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR))],
)
async def send_invite(
    tenant_id: UUID,
    body: SendInviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InviteStatusResponse:
    """
    Envia um convite por e-mail para um novo membro da instituição.
    Requer perfil de ADMIN ou COORDENADOR na tenant ativa.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    invite_repo = TenantInviteSQLAlchemyRepository(session=db)
    user_repo = UserSQLAlchemyRepository(session=db)

    use_case = SendInviteUseCase(
        tenant_repo=tenant_repo,
        member_repo=member_repo,
        invite_repo=invite_repo,
        user_repo=user_repo,
    )

    invite = await use_case.execute(
        SendInviteInput(
            tenant_id=tenant_id,
            email=body.email,
            role=body.role,
            invited_by=current_user,
            subject_class_ids=body.subject_class_ids,
        )
    )

    tenant_name = invite.tenant_name or ""
    invite.invited_by_name = current_user.name
    return _to_invite_response(invite, tenant_name)


@tenant_invites_router.get(
    "/{tenant_id}/invites/metrics",
    response_model=TenantInvitesMetricsResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR))],
)
async def get_tenant_invites_metrics(
    tenant_id: UUID,
    days: int = Query(30, ge=1, le=365, description="Janela em dias para métricas (padrão 30)"),
    db: AsyncSession = Depends(get_db),
) -> TenantInvitesMetricsResponse:
    """
    Consulta os indicadores consolidados de convites da instituição no recorte temporal selecionado.
    Requer perfil de ADMIN ou COORDENADOR.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    invite_repo = TenantInviteSQLAlchemyRepository(session=db)
    use_case = GetTenantInvitesMetricsUseCase(tenant_repo=tenant_repo, invite_repo=invite_repo)

    metrics = await use_case.execute(GetTenantInvitesMetricsInput(tenant_id=tenant_id, days=days))

    return TenantInvitesMetricsResponse(
        total=metrics.total,
        pending=metrics.pending,
        accepted=metrics.accepted,
        expired=metrics.expired,
        revoked=metrics.revoked,
        acceptance_rate=metrics.acceptance_rate,
        days=metrics.days,
    )


@tenant_invites_router.get(
    "/{tenant_id}/invites",
    response_model=PageResponse[InviteStatusResponse],
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR))],
)
async def list_tenant_invites(
    tenant_id: UUID,
    pagination: PaginationParams = Depends(get_pagination_params),
    status_filter: str | None = Query(
        None,
        alias="status",
        description="Filtrar por status (pending, accepted, expired, revoked)",
    ),
    role: UserRole | None = Query(None, description="Filtrar por papel (role)"),
    search: str | None = Query(None, description="Busca por e-mail"),
    sort_by: Literal["created_at", "email", "role", "expires_at"] = Query(
        "created_at", description="Campo para ordenação"
    ),
    order: Literal["asc", "desc"] = Query("desc", description="Direção da ordenação (asc, desc)"),
    db: AsyncSession = Depends(get_db),
) -> PageResponse[InviteStatusResponse]:
    """
    Lista convites de uma Tenant/Instituição com suporte a paginação por offset e filtros por status, papel e e-mail.
    Requer perfil de ADMIN ou COORDENADOR na tenant ativa.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    invite_repo = TenantInviteSQLAlchemyRepository(session=db)
    use_case = ListTenantInvitesUseCase(tenant_repo=tenant_repo, invite_repo=invite_repo)

    page = await use_case.execute(
        ListTenantInvitesInput(
            tenant_id=tenant_id,
            pagination=pagination,
            status=status_filter,
            role=role,
            search=search,
            sort_by=sort_by,
            order=order,
        )
    )

    tenant = await tenant_repo.find_by_id(tenant_id)
    tenant_name = tenant.name if tenant else ""
    items = [_to_invite_response(inv, tenant_name) for inv in page.items]

    return PageResponse.of(page, items)


@tenant_invites_router.post(
    "/{tenant_id}/invites/{invite_id}/resend",
    response_model=InviteStatusResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR))],
)
async def resend_invite(
    tenant_id: UUID,
    invite_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InviteStatusResponse:
    """
    Reenvia um convite (renova a validade em +7 dias, reativa se revogado e dispara novo e-mail).
    Requer perfil de ADMIN ou COORDENADOR na tenant ativa.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    invite_repo = TenantInviteSQLAlchemyRepository(session=db)
    use_case = ResendInviteUseCase(tenant_repo=tenant_repo, invite_repo=invite_repo)

    invite = await use_case.execute(
        ResendInviteInput(
            tenant_id=tenant_id,
            invite_id=invite_id,
            resender=current_user,
        )
    )

    tenant_name = invite.tenant_name or ""
    invite.invited_by_name = invite.invited_by_name or current_user.name
    return _to_invite_response(invite, tenant_name)


@tenant_invites_router.delete(
    "/{tenant_id}/invites/{invite_id}",
    response_model=InviteStatusResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR))],
)
async def revoke_invite(
    tenant_id: UUID,
    invite_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> InviteStatusResponse:
    """
    Revoga/cancela um convite pendente da instituição.
    Requer perfil de ADMIN ou COORDENADOR na tenant ativa.
    """
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    invite_repo = TenantInviteSQLAlchemyRepository(session=db)

    use_case = RevokeInviteUseCase(tenant_repo=tenant_repo, invite_repo=invite_repo)
    invite = await use_case.execute(
        RevokeInviteInput(
            tenant_id=tenant_id,
            invite_id=invite_id,
        )
    )

    tenant_name = invite.tenant_name or ""
    return _to_invite_response(invite, tenant_name)


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS SOB /invites (Tenant contextualizada pelo Token JWT)
# ══════════════════════════════════════════════════════════════════════════════


@invites_router.post(
    "",
    response_model=InviteStatusResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR))],
)
async def send_invite_current_tenant(
    body: SendInviteRequest,
    current_user: User = Depends(get_current_user),
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> InviteStatusResponse:
    """
    Envia um convite por e-mail para um novo membro da instituição ativa.
    Requer perfil de ADMIN ou COORDENADOR na tenant ativa.
    """
    return await send_invite(
        tenant_id=tenant_id,
        body=body,
        current_user=current_user,
        db=db,
    )


@invites_router.get(
    "",
    response_model=PageResponse[InviteStatusResponse],
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR))],
)
async def list_invites_current_tenant(
    pagination: PaginationParams = Depends(get_pagination_params),
    status_filter: str | None = Query(
        None,
        alias="status",
        description="Filtrar por status (pending, accepted, expired, revoked)",
    ),
    role: UserRole | None = Query(None, description="Filtrar por papel (role)"),
    search: str | None = Query(None, description="Busca por e-mail"),
    sort_by: Literal["created_at", "email", "role", "expires_at"] = Query(
        "created_at", description="Campo para ordenação"
    ),
    order: Literal["asc", "desc"] = Query("desc", description="Direção da ordenação (asc, desc)"),
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> PageResponse[InviteStatusResponse]:
    """
    Lista convites da instituição ativa sem necessidade de passar tenant_id no path.
    Requer perfil de ADMIN ou COORDENADOR na tenant ativa.
    """
    return await list_tenant_invites(
        tenant_id=tenant_id,
        pagination=pagination,
        status_filter=status_filter,
        role=role,
        search=search,
        sort_by=sort_by,
        order=order,
        db=db,
    )


@invites_router.get(
    "/metrics",
    response_model=TenantInvitesMetricsResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR))],
)
async def get_invites_metrics_current_tenant(
    days: int = Query(30, ge=1, le=365, description="Janela em dias para métricas (padrão 30)"),
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> TenantInvitesMetricsResponse:
    """
    Consulta os indicadores consolidados de convites da instituição ativa.
    Requer perfil de ADMIN ou COORDENADOR.
    """
    return await get_tenant_invites_metrics(
        tenant_id=tenant_id,
        days=days,
        db=db,
    )


@invites_router.post(
    "/{invite_id}/resend",
    response_model=InviteStatusResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR))],
)
async def resend_invite_current_tenant(
    invite_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> InviteStatusResponse:
    """
    Reenvia convite na instituição ativa.
    Requer perfil de ADMIN ou COORDENADOR.
    """
    return await resend_invite(
        tenant_id=tenant_id,
        invite_id=invite_id,
        current_user=current_user,
        db=db,
    )


@invites_router.delete(
    "/{invite_id}",
    response_model=InviteStatusResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR))],
)
async def revoke_invite_current_tenant(
    invite_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> InviteStatusResponse:
    """
    Revoga convite na instituição ativa.
    Requer perfil de ADMIN ou COORDENADOR.
    """
    return await revoke_invite(
        tenant_id=tenant_id,
        invite_id=invite_id,
        db=db,
    )


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS PÚBLICAS / DE ACEITE POR TOKEN
# ══════════════════════════════════════════════════════════════════════════════


@invites_router.get(
    "/{token}",
    response_model=InviteStatusResponse,
)
async def get_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> InviteStatusResponse:
    """
    Consulta os detalhes de um convite a partir do token (Endpoint público).
    """
    invite_repo = TenantInviteSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)

    use_case = GetInviteUseCase(invite_repo=invite_repo, tenant_repo=tenant_repo)
    result = await use_case.execute(token)
    return _to_invite_response(result.invite, result.tenant_name)


@invites_router.post(
    "/{token}/accept",
    response_model=TenantMemberResponse,
)
async def accept_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantMemberResponse:
    """
    Aceita um convite para entrar em uma instituição.
    Requer que o usuário esteja autenticado e que seu e-mail coincida com o e-mail do convite.
    """
    invite_repo = TenantInviteSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    enrollment_repo = EnrollmentSQLAlchemyRepository(session=db)

    use_case = AcceptInviteUseCase(
        invite_repo=invite_repo,
        member_repo=member_repo,
        enrollment_repo=enrollment_repo,
    )
    member = await use_case.execute(token=token, user=current_user)

    return TenantMemberResponse(
        id=member.id,
        tenant_id=member.tenant_id,
        user_id=member.user_id,
        role=member.role,
        created_at=member.created_at,
    )
