from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.user.domain.entities.user import User
from modules.user.infra.repositories.user_sqlalchemy_repository import UserSQLAlchemyRepository
from security.jwt import decode_access_token
from shared.enums.user_role import UserRole

bearer_scheme = HTTPBearer()


@dataclass
class AuthContext:
    """Contexto completo de uma requisição autenticada."""
    user: User
    tenant_id: UUID | None        # None se o usuário não selecionou uma tenant ainda
    role: UserRole | None         # None se ainda não está em contexto de tenant


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")

    user_id = UUID(payload["sub"])
    repository = UserSQLAlchemyRepository(session=db)
    user = await repository.find_by_id(user_id)

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado.")

    raw_tenant_id = payload.get("tenant_id")
    raw_role = payload.get("role")

    return AuthContext(
        user=user,
        tenant_id=UUID(raw_tenant_id) if raw_tenant_id else None,
        role=UserRole(raw_role) if raw_role else None,
    )


async def get_current_user(
    ctx: AuthContext = Depends(get_auth_context),
) -> User:
    return ctx.user
