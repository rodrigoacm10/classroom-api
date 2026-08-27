from uuid import UUID

from modules.user.domain.entities.user import User


class FakeUserRepository:
    """
    Implementação em memória do UserRepository.
    Satisfaz o Protocol sem tocar em banco de dados.
    Usado exclusivamente em testes unitários.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, User] = {}

    async def find_by_id(self, user_id: UUID) -> User | None:
        return self._store.get(user_id)

    async def find_by_email(self, email: str) -> User | None:
        return next(
            (u for u in self._store.values() if u.email == email),
            None,
        )

    async def save(self, user: User) -> User:
        self._store[user.id] = user
        return user

    # ─── helpers de setup ────────────────────────────────────────────────────

    def seed(self, user: User) -> None:
        """Pré-popula o repositório com um usuário sem passar pelo save assíncrono."""
        self._store[user.id] = user
