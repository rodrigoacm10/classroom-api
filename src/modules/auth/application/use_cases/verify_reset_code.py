import json
from dataclasses import dataclass

from infra.cache.redis_client import redis_client
from shared.exceptions import BusinessRuleException


@dataclass
class VerifyResetCodeInput:
    email: str
    code: str


class VerifyResetCodeUseCase:
    """
    Valida previamente o código OTP de 6 dígitos no Redis.
    Segurança:
    - Limite de até 5 tentativas incorretas antes de destruir a chave (anti-força bruta).
    - Preserva a chave intacta quando o código estiver correto para que o use_case de reset_password possa utilizá-la.
    """

    def __init__(self, redis=redis_client) -> None:
        self.redis = redis

    async def execute(self, data: VerifyResetCodeInput) -> None:
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
