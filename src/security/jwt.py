from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from config.settings import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 horas


def create_access_token(
    user_id: UUID,
    tenant_id: UUID | None = None,
    role: str | None = None,
) -> str:
    """
    Gera um token JWT.

    - Sem tenant_id/role: token base (logo após o login).
    - Com tenant_id/role: token enriquecido (após switch-tenant).
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decodifica e valida o token JWT.
    Lança jwt.ExpiredSignatureError ou jwt.InvalidTokenError em caso de falha.
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
