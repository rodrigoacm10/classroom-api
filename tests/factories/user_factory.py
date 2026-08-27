import uuid
from uuid import UUID

from modules.user.domain.entities.user import User
from security.password import hash_password


class UserFactory:
    """Factory para criar entidades User com valores padrão para testes."""

    @staticmethod
    def make(**overrides) -> User:
        """
        Cria uma entidade User em memória com valores padrão.
        Qualquer campo pode ser sobrescrito via kwargs.

        O `password_hash` padrão é um placeholder — use `make_with_password()`
        quando precisar que a verificação de senha funcione de verdade.
        """
        defaults: dict = {
            "id": uuid.uuid4(),
            "name": "John Doe",
            "email": "john@example.com",
            "password_hash": "hashed_placeholder",
        }
        merged = {**defaults, **overrides}
        if isinstance(merged["id"], str):
            merged["id"] = UUID(merged["id"])
        return User(**merged)

    @staticmethod
    def make_with_password(plain_password: str, **overrides) -> User:
        """
        Cria um User cujo password_hash é o hash real de `plain_password`.
        Use em testes que verificam autenticação de senha (LoginUseCase).
        """
        return UserFactory.make(
            password_hash=hash_password(plain_password),
            **overrides,
        )

    @staticmethod
    async def create(session, **overrides):
        """
        Cria e persiste um UserModel no banco de dados de teste.
        Use apenas em testes de integração e E2E.

        O email é único por padrão (via sufixo UUID) para evitar colisões de
        constraint UNIQUE quando vários testes rodam na mesma sessão de DB.
        """
        from infra.database.models.user import UserModel

        defaults: dict = {
            "id": uuid.uuid4(),
            "name": "John Doe",
            "email": f"john_{uuid.uuid4().hex[:8]}@example.com",
            "password_hash": "hashed_placeholder",
            "fcm_token": None,
        }
        data = {**defaults, **overrides}
        if isinstance(data["id"], str):
            data["id"] = UUID(data["id"])

        model = UserModel(**data)
        session.add(model)
        await session.flush()   # INSERT imediato, mas dentro da transação (sem commit)
        await session.refresh(model)
        return model
