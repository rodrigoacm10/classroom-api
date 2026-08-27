from typing import Protocol
from uuid import UUID

from modules.user.domain.entities.user import User


class UserRepository(Protocol):

    async def find_by_id(self, user_id: UUID) -> User | None: ...

    async def find_by_email(self, email: str) -> User | None: ...

    async def save(self, user: User) -> User: ...
