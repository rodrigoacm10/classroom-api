from dataclasses import dataclass

from modules.user.domain.entities.user import User
from modules.user.domain.repositories.user_repository import UserRepository
from security.password import hash_password_async


@dataclass
class CreateUserInput:
    name: str
    email: str
    password: str


class CreateUserUseCase:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def execute(self, data: CreateUserInput) -> User:
        existing = await self.repository.find_by_email(data.email)
        if existing:
            raise ValueError("E-mail já cadastrado.")

        password_hash = await hash_password_async(data.password)
        user = User(
            name=data.name,
            email=data.email,
            password_hash=password_hash,
        )

        return await self.repository.save(user)
