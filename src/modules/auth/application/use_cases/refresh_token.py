from dataclasses import dataclass
from uuid import UUID

import jwt

from modules.user.domain.repositories.user_repository import UserRepository
from security.blacklist import is_token_blacklisted
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
        if jti and await is_token_blacklisted(jti):
            raise ValueError("Refresh token revogado.")

        user_id = UUID(payload["sub"])
        user = await self.user_repo.find_by_id(user_id)
        if not user:
            raise ValueError("Usuário não encontrado.")

        # Gera novos tokens
        new_access_token = create_access_token(user_id=user.id)
        new_refresh_token = create_refresh_token(user_id=user.id)

        return RefreshTokenOutput(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
        )
