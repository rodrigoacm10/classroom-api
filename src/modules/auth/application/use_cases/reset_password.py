import json
from dataclasses import dataclass
from uuid import UUID

from config.settings import settings
from infra.cache.redis_client import redis_client
from modules.user.domain.repositories.user_repository import UserRepository
from security.blacklist import revoke_user_sessions
from security.password import hash_password
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class ResetPasswordInput:
    email: str
    code: str
    new_password: str


class ResetPasswordUseCase:
    """
    Confirma o código OTP de 6 dígitos e cadastra a nova senha do usuário.
    Segurança:
    - Uso único do código (deletado do Redis no primeiro sucesso).
    - Limite de até 5 tentativas incorretas antes de destruir a chave (anti-força bruta).
    - Invalidação global de todas as sessões e tokens JWT anteriores do usuário.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        redis=redis_client,
    ) -> None:
        self.user_repo = user_repo
        self.redis = redis

    async def execute(self, data: ResetPasswordInput) -> None:
        if len(data.new_password) < 6:
            raise BusinessRuleException("A nova senha deve ter no mínimo 6 caracteres.")

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

        # Código correto: busca o usuário e atualiza a senha
        user_id = UUID(stored_data["user_id"])
        user = await self.user_repo.find_by_id(user_id)
        if not user:
            raise ResourceNotFoundException("Usuário não encontrado.")

        user.password_hash = hash_password(data.new_password)
        await self.user_repo.save(user)

        # Deleta a chave de recuperação (uso único)
        await self.redis.delete(redis_key)

        # Invalida todas as sessões e tokens JWT anteriores do usuário
        ttl_sessions = settings.refresh_token_expire_days * 86400
        await revoke_user_sessions(user.id, expire_seconds=ttl_sessions)
