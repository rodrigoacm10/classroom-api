from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.tenant.application.use_cases.accept_invite import AcceptInviteUseCase
from modules.tenant.application.use_cases.get_invite import GetInviteUseCase
from modules.tenant.application.use_cases.revoke_invite import (
    RevokeInviteInput,
    RevokeInviteUseCase,
)
from modules.tenant.application.use_cases.send_invite import (
    SendInviteInput,
    SendInviteUseCase,
)
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
    TenantMemberResponse,
)
from modules.user.domain.entities.user import User
from modules.user.infra.repositories.user_sqlalchemy_repository import UserSQLAlchemyRepository
from security.dependencies.current_user import get_current_user
from security.dependencies.require_role import require_role
from shared.enums.user_role import UserRole

tenant_invites_router = APIRouter(prefix="/tenants", tags=["Invites"])
invites_router = APIRouter(prefix="/invites", tags=["Invites"])


@tenant_invites_router.post(
    "/{tenant_id}/invites",
    response_model=InviteStatusResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def send_invite(
    tenant_id: UUID,
    body: SendInviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InviteStatusResponse:
    """
    Envia um convite por e-mail para um novo membro da instituição.
    Requer perfil de ADMIN na tenant ativa.
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
        )
    )

    tenant = await tenant_repo.find_by_id(tenant_id)
    tenant_name = tenant.name if tenant else ""

    return InviteStatusResponse(
        id=invite.id,
        tenant_id=invite.tenant_id,
        tenant_name=tenant_name,
        email=invite.email,
        role=invite.role,
        token=invite.token,
        status="pending",
        expires_at=invite.expires_at,
        created_at=invite.created_at,
    )


@tenant_invites_router.delete(
    "/{tenant_id}/invites/{invite_id}",
    response_model=InviteStatusResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def revoke_invite(
    tenant_id: UUID,
    invite_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> InviteStatusResponse:
    """
    Revoga/cancela um convite pendente da instituição.
    Requer perfil de ADMIN na tenant ativa.
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

    tenant = await tenant_repo.find_by_id(tenant_id)
    tenant_name = tenant.name if tenant else ""

    return InviteStatusResponse(
        id=invite.id,
        tenant_id=invite.tenant_id,
        tenant_name=tenant_name,
        email=invite.email,
        role=invite.role,
        token=invite.token,
        status="revoked",
        expires_at=invite.expires_at,
        created_at=invite.created_at,
    )


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

    return InviteStatusResponse(
        id=result.invite.id,
        tenant_id=result.invite.tenant_id,
        tenant_name=result.tenant_name,
        email=result.invite.email,
        role=result.invite.role,
        token=result.invite.token,
        status=result.status,
        expires_at=result.invite.expires_at,
        created_at=result.invite.created_at,
    )


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

    use_case = AcceptInviteUseCase(invite_repo=invite_repo, member_repo=member_repo)
    member = await use_case.execute(token=token, user=current_user)

    return TenantMemberResponse(
        id=member.id,
        tenant_id=member.tenant_id,
        user_id=member.user_id,
        role=member.role,
        created_at=member.created_at,
    )
