from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.user.domain.entities.user import User
from modules.user.infra.repositories.user_sqlalchemy_repository import UserSQLAlchemyRepository
from security.blacklist import check_token_and_session_revocation
from security.jwt import decode_access_token
from shared.enums.user_role import UserRole

bearer_scheme = HTTPBearer()


@dataclass
class AuthContext:
    """Contexto completo de uma requisição autenticada."""

    user: User
    tenant_id: UUID | None
    role: UserRole | None
    jti: str | None
    token_exp: int | None


async def _validate_access_token_payload(
    credentials: HTTPAuthorizationCredentials,
) -> tuple[dict, UUID, str | None]:
    """
    Decodifica o JWT de acesso e valida revogação no Redis em 1 único round-trip (MGET),
    sem abrir conexão com o PostgreSQL.
    """
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")

    # Garante que um Refresh Token não possa ser usado como Access Token
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tipo de token inválido. Esperado token de acesso.",
        )

    jti = payload.get("jti")
    user_id = UUID(payload["sub"])
    token_iat = payload.get("iat")

    is_blacklisted, is_session_revoked = await check_token_and_session_revocation(
        jti=jti,
        user_id=user_id,
        token_iat=token_iat,
    )

    if is_blacklisted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revogado (logout efetuado).",
        )

    if is_session_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão encerrada por alteração de senha. Faça login novamente.",
        )

    return payload, user_id, jti


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    payload, user_id, jti = await _validate_access_token_payload(credentials)

    repository = UserSQLAlchemyRepository(session=db)
    user = await repository.find_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado."
        )

    raw_tenant_id = payload.get("tenant_id")
    raw_role = payload.get("role")

    return AuthContext(
        user=user,
        tenant_id=UUID(raw_tenant_id) if raw_tenant_id else None,
        role=UserRole(raw_role) if raw_role else None,
        jti=jti,
        token_exp=payload.get("exp"),
    )


async def get_token_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AuthContext:
    """
    Contexto leve de autenticação baseado exclusivamente nas claims assinadas do JWT + Redis.
    Evita o `SELECT * FROM users` em rotas de alta vazão (como `/confirm`) onde a própria
    query de domínio já valida o vínculo do `user_id` no banco de dados.
    """
    payload, user_id, jti = await _validate_access_token_payload(credentials)

    raw_tenant_id = payload.get("tenant_id")
    raw_role = payload.get("role")

    lightweight_user = User(
        id=user_id,
        name="",
        email="",
        password_hash="",
    )

    return AuthContext(
        user=lightweight_user,
        tenant_id=UUID(raw_tenant_id) if raw_tenant_id else None,
        role=UserRole(raw_role) if raw_role else None,
        jti=jti,
        token_exp=payload.get("exp"),
    )


async def get_tenant_token_auth_context(
    ctx: AuthContext = Depends(get_token_auth_context),
) -> AuthContext:
    """
    Variante de `get_token_auth_context` que exige `tenant_id` selecionado no token,
    sem realizar query extra na tabela `users`.
    """
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nenhuma tenant selecionada. Use POST /auth/switch-tenant.",
        )
    return ctx


async def get_current_user(
    ctx: AuthContext = Depends(get_auth_context),
) -> User:
    return ctx.user


async def get_current_tenant_id(
    ctx: AuthContext = Depends(get_auth_context),
) -> UUID:
    """Extrai o ID da tenant ativa do contexto de autenticação (JWT)."""
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nenhuma tenant selecionada. Use POST /auth/switch-tenant.",
        )
    return ctx.tenant_id
