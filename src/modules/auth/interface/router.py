from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
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

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * settings.refresh_token_expire_days


# ─────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    client_type: Literal["web", "mobile"] = "mobile"
    """
    Define como o Refresh Token será entregue:
    - "mobile": retornado no body (para React Native/AsyncStorage).
    - "web"   : enviado como Cookie HttpOnly (para browsers/dashboard).
    """


class SwitchTenantRequest(BaseModel):
    tenant_id: UUID


class RefreshTokenRequest(BaseModel):
    refresh_token: str | None = None
    """
    Clients mobile enviam o token aqui.
    Clients web omitem este campo — o token é lido do Cookie HttpOnly automaticamente.
    """


class LoginMobileResponse(BaseModel):
    """Resposta para clientes mobile: ambos os tokens no body."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginWebResponse(BaseModel):
    """Resposta para clientes web: apenas o access_token no body; refresh_token vai no Cookie HttpOnly."""
    access_token: str
    token_type: str = "bearer"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def _set_refresh_cookie(response: Response, token: str) -> None:
    """Define o Cookie HttpOnly com o Refresh Token para clientes web."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,                       # ✅ JS não consegue ler este cookie
        secure=settings.cookie_secure,       # True em produção (HTTPS)
        samesite=settings.cookie_samesite,   # "lax" dev / "strict" prod (proteção CSRF)
        max_age=REFRESH_COOKIE_MAX_AGE,      # TTL = 7 dias (em segundos)
        path="/auth",                        # Cookie visível apenas nas rotas /auth/*
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Limpa o Cookie do Refresh Token no logout de clientes web."""
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/auth")


# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────

@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginMobileResponse | LoginWebResponse:
    """
    Autentica o usuário via e-mail e senha.

    - **mobile**: Retorna `access_token` + `refresh_token` no body JSON.
    - **web**: Retorna apenas `access_token` no body; `refresh_token` vai em Cookie HttpOnly (`refresh_token`).

    Limitado a **5 tentativas por minuto** por IP.
    """
    repository = UserSQLAlchemyRepository(session=db)
    use_case = LoginUseCase(repository=repository)

    try:
        result = await use_case.execute(LoginInput(email=body.email, password=body.password))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    if body.client_type == "web":
        _set_refresh_cookie(response, result.refresh_token)
        return LoginWebResponse(access_token=result.access_token)

    # client_type == "mobile": ambos os tokens no body
    return LoginMobileResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
    )


@router.post("/refresh")
async def refresh_token(
    response: Response,
    body: RefreshTokenRequest = RefreshTokenRequest(),
    # Cookie lido automaticamente pelo FastAPI para clientes web
    cookie_refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> LoginMobileResponse | LoginWebResponse:
    """
    Renova os tokens utilizando o Refresh Token.

    - **mobile**: envia `{ "refresh_token": "..." }` no body.
    - **web**: não precisa enviar nada; o browser envia o Cookie HttpOnly automaticamente.
    """
    # Prioriza o token do body (mobile); fallback para o cookie (web)
    token_to_use = body.refresh_token or cookie_refresh_token

    if not token_to_use:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token não encontrado no body nem no cookie.",
        )

    user_repo = UserSQLAlchemyRepository(session=db)
    use_case = RefreshTokenUseCase(user_repo=user_repo)

    try:
        result = await use_case.execute(RefreshTokenInput(refresh_token=token_to_use))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    # Se o refresh chegou via Cookie, renova o cookie e retorna só o access token (web)
    if cookie_refresh_token and not body.refresh_token:
        _set_refresh_cookie(response, result.refresh_token)
        return LoginWebResponse(access_token=result.access_token)

    # Se chegou via body, retorna ambos no body (mobile)
    return LoginMobileResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
    )


@router.post("/switch-tenant", response_model=TokenResponse)
async def switch_tenant(
    body: SwitchTenantRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Recebe o JWT base (sem tenant) e devolve um JWT enriquecido com `tenant_id` + `role`.
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

    return TokenResponse(access_token=result.access_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    auth_context: AuthContext = Depends(get_auth_context),
    # Cookie lido automaticamente (clientes web)
    cookie_refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> MessageResponse:
    """
    Efetua o logout:
    - Revoga o Access Token adicionando o JTI à blacklist no Redis.
    - Se cliente web: limpa o Cookie HttpOnly do Refresh Token.
    """
    use_case = LogoutUseCase()
    await use_case.execute(auth_context)

    if cookie_refresh_token:
        _clear_refresh_cookie(response)

    return MessageResponse(message="Logout realizado com sucesso. Token revogado.")
