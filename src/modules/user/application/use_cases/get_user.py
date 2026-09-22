from uuid import UUID

from modules.user.domain.entities.user import User
from modules.user.domain.repositories.user_repository import UserRepository


class GetUserUseCase:

    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def execute(self, user_id: UUID) -> User:
        user = await self.repository.find_by_id(user_id)
        if not user:
            raise ValueError("Usuário não encontrado.")
        return user
