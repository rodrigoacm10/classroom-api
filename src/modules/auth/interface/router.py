from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.auth.application.use_cases.login import LoginInput, LoginUseCase
from modules.auth.application.use_cases.logout import LogoutUseCase
from modules.auth.application.use_cases.refresh_token import (
    RefreshTokenInput,
    RefreshTokenUseCase,
)
from modules.auth.application.use_cases.switch_tenant import SwitchTenantInput, SwitchTenantUseCase
from modules.tenant.infra.repositories.tenant_member_sqlalchemy_repository import (
    TenantMemberSQLAlchemyRepository,
)
from modules.user.domain.entities.user import User
from modules.user.infra.repositories.user_sqlalchemy_repository import UserSQLAlchemyRepository
from security.dependencies.current_user import AuthContext, get_auth_context, get_current_user
from security.rate_limiter import limiter

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SwitchTenantRequest(BaseModel):
    tenant_id: UUID


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """
    Realiza a autenticação global do usuário via e-mail e senha.
    Retorna o Access Token (base) e o Refresh Token.
    Limitado a 5 tentativas por minuto por IP.
    """
    repository = UserSQLAlchemyRepository(session=db)
    use_case = LoginUseCase(repository=repository)

    try:
        result = await use_case.execute(LoginInput(email=body.email, password=body.password))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    return LoginResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """
    Renova o Access Token e Refresh Token utilizando um Refresh Token válido.
    """
    user_repo = UserSQLAlchemyRepository(session=db)
    use_case = RefreshTokenUseCase(user_repo=user_repo)

    try:
        result = await use_case.execute(RefreshTokenInput(refresh_token=body.refresh_token))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    return LoginResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
    )


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


@router.post("/logout", response_model=MessageResponse)
async def logout(
    auth_context: AuthContext = Depends(get_auth_context),
) -> MessageResponse:
    """
    Efetua o logout revogando o token ativo e adicionando o JTI à blacklist no Redis.
    """
    use_case = LogoutUseCase()
    await use_case.execute(auth_context)
    return MessageResponse(message="Logout realizado com sucesso. Token revogado.")
