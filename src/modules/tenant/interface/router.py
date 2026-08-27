from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
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
from modules.tenant.application.use_cases.list_my_tenants import ListMyTenantsUseCase
from modules.tenant.infra.repositories.tenant_member_sqlalchemy_repository import (
    TenantMemberSQLAlchemyRepository,
)
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import (
    TenantSQLAlchemyRepository,
)
from modules.tenant.interface.schemas.tenant_schemas import (
    AddTenantMemberRequest,
    CreateTenantRequest,
    MyTenantResponse,
    TenantMemberResponse,
    TenantResponse,
)
from modules.user.domain.entities.user import User
from security.dependencies.current_user import get_current_user
from security.dependencies.require_role import require_role
from shared.enums.user_role import UserRole

router = APIRouter(prefix="/tenants", tags=["Tenants"])


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
