import json
from dataclasses import dataclass
from uuid import UUID

from config.settings import settings
from infra.cache.redis_client import redis_client
from security.jwt import create_reset_password_token
from shared.exceptions import BusinessRuleException


@dataclass
class VerifyResetCodeInput:
    email: str
    code: str


@dataclass
class VerifyResetCodeOutput:
    reset_token: str
    token_type: str = "Bearer"
    expires_in: int = 600


class VerifyResetCodeUseCase:
    """
    Valida o código OTP de 6 dígitos no Redis (Etapa 2 - Abordagem B).
    Segurança:
    - Limite de até 5 tentativas incorretas antes de destruir a chave (anti-força bruta).
    - Quando o código estiver correto, destrói a chave do OTP no Redis imediatamente (uso único).
    - Emite um reset_token temporário (JWT) de alta entropia para a etapa 3 de troca de senha.
    """

    def __init__(self, redis=redis_client) -> None:
        self.redis = redis

    async def execute(self, data: VerifyResetCodeInput) -> VerifyResetCodeOutput:
        email_clean = data.email.strip().lower()
        redis_key = f"password_reset:{email_clean}"

        raw_data = await self.redis.get(redis_key)
        if not raw_data:
            raise BusinessRuleException("Código de recuperação inválido ou expirado.")

        stored_data = json.loads(raw_data)
        stored_code = stored_data.get("code")
        attempts = int(stored_data.get("attempts", 0))

        if data.code.strip() != stored_code:
            attempts += 1
            if attempts >= 5:
                await self.redis.delete(redis_key)
                raise BusinessRuleException(
                    "Limite de tentativas excedido. Solicite um novo código de recuperação."
                )

            # Preserva o TTL restante e atualiza a contagem de tentativas no Redis
            ttl = await self.redis.ttl(redis_key)
            if ttl and ttl > 0:
                stored_data["attempts"] = attempts
                await self.redis.set(redis_key, json.dumps(stored_data), ex=ttl)

            raise BusinessRuleException("Código de recuperação incorreto.")

        # Código correto: destrói o OTP imediatamente no Redis (single-use)
        await self.redis.delete(redis_key)

        user_id_str = stored_data.get("user_id")
        if not user_id_str:
            raise BusinessRuleException("Código de recuperação inválido ou expirado.")

        user_id = UUID(user_id_str)
        expires_minutes = settings.password_reset_token_expire_minutes
        reset_token = create_reset_password_token(user_id=user_id, expire_minutes=expires_minutes)

        return VerifyResetCodeOutput(
            reset_token=reset_token,
            token_type="Bearer",
            expires_in=expires_minutes * 60,
        )
