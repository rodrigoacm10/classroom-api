from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from config.settings import settings
from infra.cache.redis_client import redis_client
from modules.user.domain.repositories.user_repository import UserRepository
from security.blacklist import revoke_user_sessions
from security.jwt import decode_reset_password_token
from security.password import hash_password
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class ResetPasswordInput:
    reset_token: str
    new_password: str


class ResetPasswordUseCase:
    """
    Confirma o reset_token temporário (Etapa 3 - Abordagem B) e cadastra a nova senha do usuário.
    Segurança:
    - Uso único do token (JTI é gravado na blacklist do Redis com TTL restante).
    - Validação de expiração e integridade criptográfica do JWT (HS256).
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

        try:
            payload = decode_reset_password_token(data.reset_token)
        except ExpiredSignatureError:
            raise BusinessRuleException("Token de recuperação expirado. Solicite um novo código.")
        except InvalidTokenError:
            raise BusinessRuleException("Token de recuperação inválido.")

        jti = payload.get("jti")
        user_id_str = payload.get("sub")
        exp = payload.get("exp")

        if not jti or not user_id_str:
            raise BusinessRuleException("Token de recuperação inválido.")

        # Verifica se o token já foi utilizado anteriormente (blacklist por JTI)
        is_revoked = await self.redis.get(f"blacklist:{jti}")
        if is_revoked:
            raise BusinessRuleException("Token de recuperação já utilizado.")

        user_id = UUID(user_id_str)
        user = await self.user_repo.find_by_id(user_id)
        if not user:
            raise ResourceNotFoundException("Usuário não encontrado.")

        # Atualiza a senha
        user.password_hash = hash_password(data.new_password)
        await self.user_repo.save(user)

        # Adiciona o JTI na blacklist até o término do tempo de vida do token (single-use)
        now_ts = int(datetime.now(timezone.utc).timestamp())
        remaining_ttl = max(int(exp - now_ts), 1) if exp else settings.password_reset_token_expire_minutes * 60
        await self.redis.set(f"blacklist:{jti}", "revoked", ex=remaining_ttl)

        # Invalida todas as sessões e tokens JWT anteriores do usuário
        ttl_sessions = settings.refresh_token_expire_days * 86400
        await revoke_user_sessions(user.id, expire_seconds=ttl_sessions)
