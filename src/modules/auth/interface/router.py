from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.auth.application.use_cases.login import LoginInput, LoginUseCase
from modules.auth.application.use_cases.switch_tenant import SwitchTenantInput, SwitchTenantUseCase
from modules.tenant.infra.repositories.tenant_member_sqlalchemy_repository import (
    TenantMemberSQLAlchemyRepository,
)
from modules.user.domain.entities.user import User
from modules.user.infra.repositories.user_sqlalchemy_repository import UserSQLAlchemyRepository
from security.dependencies.current_user import get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SwitchTenantRequest(BaseModel):
    tenant_id: UUID


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    repository = UserSQLAlchemyRepository(session=db)
    use_case = LoginUseCase(repository=repository)

    try:
        result = await use_case.execute(LoginInput(email=body.email, password=body.password))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    return TokenResponse(access_token=result.access_token, token_type=result.token_type)


@router.post("/switch-tenant", response_model=TokenResponse)
async def switch_tenant(
    body: SwitchTenantRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Recebe o JWT base (sem tenant) e devolve um JWT enriquecido com tenant_id + role.
    Requer que o usuário seja membro da tenant informada.
    """
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = SwitchTenantUseCase(member_repo=member_repo)

    try:
        result = await use_case.execute(
            SwitchTenantInput(user=current_user, tenant_id=body.tenant_id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return TokenResponse(access_token=result.access_token, token_type=result.token_type)
