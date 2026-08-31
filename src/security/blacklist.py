from datetime import datetime, timezone
from uuid import UUID

from infra.cache.redis_client import redis_client


async def add_token_to_blacklist(jti: str, expire_seconds: int) -> None:
    """
    Adiciona o JTI (identificador único do token JWT) à blacklist do Redis.
    O TTL (tempo de vida) no Redis é ajustado para o tempo restante até a expiração do token.
    """
    if expire_seconds > 0:
        await redis_client.set(f"blacklist:{jti}", "revoked", ex=expire_seconds)


async def is_token_blacklisted(jti: str | None) -> bool:
    """
    Verifica se o JTI está presente na blacklist do Redis.
    """
    if not jti:
        return False
    result = await redis_client.get(f"blacklist:{jti}")
    return result is not None


async def revoke_user_sessions(user_id: UUID | str, expire_seconds: int = 7 * 86400) -> None:
    """
    Registra no Redis um timestamp a partir do qual todos os tokens emitidos anteriormente
    para este usuário são considerados invalidados (usado em troca de senha).
    """
    now_ts = datetime.now(timezone.utc).timestamp()
    await redis_client.set(f"user_revoked_before:{user_id}", str(now_ts), ex=expire_seconds)


async def is_user_session_revoked(user_id: UUID | str, token_iat: int | float | None) -> bool:
    """
    Verifica se as sessões do usuário foram invalidadas após a emissão do token informado.
    """
    revoked_before = await redis_client.get(f"user_revoked_before:{user_id}")
    if not revoked_before:
        return False

    if token_iat is None:
        # Se por algum motivo o token não possuir a claim iat, considera revogado por segurança
        return True

    return float(token_iat) < float(revoked_before)
