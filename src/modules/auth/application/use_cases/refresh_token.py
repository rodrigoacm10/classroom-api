from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import jwt

from modules.user.domain.repositories.user_repository import UserRepository
from security.blacklist import add_token_to_blacklist, is_token_blacklisted, revoke_user_sessions
from security.jwt import create_access_token, create_refresh_token, decode_access_token


@dataclass
class RefreshTokenInput:
    refresh_token: str


@dataclass
class RefreshTokenOutput:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenUseCase:
    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    async def execute(self, data: RefreshTokenInput) -> RefreshTokenOutput:
        try:
            payload = decode_access_token(data.refresh_token)
        except jwt.ExpiredSignatureError:
            raise ValueError("Refresh token expirado.")
        except jwt.InvalidTokenError:
            raise ValueError("Refresh token inválido.")

        if payload.get("type") != "refresh":
            raise ValueError("O token fornecido não é um token de refresh.")

        jti = payload.get("jti")
        user_id = UUID(payload["sub"])

        # Detecção de Reúso de Token (OAuth 2.0 Security BCP / RFC 6819 § 5.2.2.3):
        # Se um token já revogado for reutilizado, indica que o token foi interceptado/clonado.
        # Por segurança, todas as sessões anteriores do usuário são revogadas.
        if jti and await is_token_blacklisted(jti):
            try:
                await revoke_user_sessions(user_id)
            except Exception:
                pass
            raise ValueError("Refresh token revogado.")

        user = await self.user_repo.find_by_id(user_id)
        if not user:
            raise ValueError("Usuário não encontrado.")

        # Preserva o escopo da tenant ativa (se o token anterior já estava associado a uma tenant)
        raw_tenant_id = payload.get("tenant_id")
        tenant_id = UUID(raw_tenant_id) if raw_tenant_id else None
        role = payload.get("role")

        # Rotação de Refresh Token (RTR): invalida imediatamente o refresh token anterior
        # para que ele nunca mais possa ser reutilizado
        exp = payload.get("exp")
        if jti and exp:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            remaining_seconds = exp - now_ts
            if remaining_seconds > 0:
                try:
                    await add_token_to_blacklist(jti=jti, expire_seconds=remaining_seconds)
                except Exception:
                    pass

        # Gera novo par de tokens (Access Token com TTL curto + novo Refresh Token com novo JTI)
        new_access_token = create_access_token(
            user_id=user.id,
            tenant_id=tenant_id,
            role=role,
        )
        new_refresh_token = create_refresh_token(
            user_id=user.id,
            tenant_id=tenant_id,
            role=role,
        )

        return RefreshTokenOutput(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
        )
