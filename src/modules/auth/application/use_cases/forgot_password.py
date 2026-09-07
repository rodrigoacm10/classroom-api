import json
import secrets
from dataclasses import dataclass

from config.settings import settings
from infra.cache.redis_client import redis_client
from infra.email.resend_client import send_password_reset_email
from modules.user.domain.repositories.user_repository import UserRepository


@dataclass
class ForgotPasswordInput:
    email: str


class ForgotPasswordUseCase:
    """
    Solicita o envio de código OTP de recuperação de senha por e-mail.
    Segurança:
    - Retorno idêntico e silencioso mesmo se o e-mail não existir (anti-enumeração).
    - Código de 6 dígitos numéricos aleatórios com TTL no Redis (padrão: 15 min).
    - Sucesso/falha no envio de e-mail são logados dentro do próprio resend_client.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        redis=redis_client,
    ) -> None:
        self.user_repo = user_repo
        self.redis = redis

    async def execute(self, data: ForgotPasswordInput) -> None:
        email_clean = data.email.strip().lower()
        user = await self.user_repo.find_by_email(email_clean)

        if not user:
            return

        # Gera código numérico de 6 dígitos criptograficamente seguro (ex: 749201)
        code = f"{secrets.randbelow(1_000_000):06d}"

        ttl_seconds = settings.password_reset_expire_minutes * 60
        payload = json.dumps(
            {
                "code": code,
                "user_id": str(user.id),
                "attempts": 0,
            }
        )

        redis_key = f"password_reset:{email_clean}"
        await self.redis.set(redis_key, payload, ex=ttl_seconds)

        send_password_reset_email(
            to_email=user.email,
            user_name=user.name,
            code=code,
            expires_in_minutes=settings.password_reset_expire_minutes,
        )