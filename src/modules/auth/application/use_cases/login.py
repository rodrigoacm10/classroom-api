from dataclasses import dataclass

from modules.user.domain.repositories.user_repository import UserRepository
from security.jwt import create_access_token
from security.password import verify_password


@dataclass
class LoginInput:
    email: str
    password: str


@dataclass
class LoginOutput:
    access_token: str
    token_type: str = "bearer"


class LoginUseCase:

    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def execute(self, data: LoginInput) -> LoginOutput:
        user = await self.repository.find_by_email(data.email)

        if not user or not verify_password(data.password, user.password_hash):
            raise ValueError("Credenciais inválidas.")

        # Token base: identifica o usuário, mas sem contexto de tenant
        token = create_access_token(user_id=user.id)
        return LoginOutput(access_token=token)
