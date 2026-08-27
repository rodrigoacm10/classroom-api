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
