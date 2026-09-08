from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt

from config.settings import settings

ALGORITHM = "HS256"


def create_access_token(
    user_id: UUID,
    tenant_id: UUID | None = None,
    role: str | None = None,
    expire_minutes: int | None = None,
) -> str:
    """
    Gera um Access Token JWT.
    Inclui um JTI (JWT ID) único para permitir revogação/blacklist no Redis
    e IAT (Issued At) para validação de revogação por data de emissão.
    """
    now = datetime.now(timezone.utc)
    delta = timedelta(minutes=expire_minutes or settings.access_token_expire_minutes)
    expire = now + delta

    payload: dict = {
        "jti": str(uuid4()),
        "sub": str(user_id),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    """
    Gera um Refresh Token de longa duração (ex: 7 dias).
    Usado exclusivamente no endpoint /auth/refresh para gerar novos Access Tokens.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.refresh_token_expire_days)

    payload: dict = {
        "jti": str(uuid4()),
        "sub": str(user_id),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decodifica e valida o token JWT.
    Lança jwt.ExpiredSignatureError ou jwt.InvalidTokenError em caso de falha.
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
