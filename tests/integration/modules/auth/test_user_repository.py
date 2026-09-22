import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from modules.user.infra.repositories.user_sqlalchemy_repository import (
    UserSQLAlchemyRepository,
)
from tests.factories.user_factory import UserFactory


class TestUserSQLAlchemyRepository:
    """
    Testes de integração para UserSQLAlchemyRepository.

    Validam que as queries SQLAlchemy funcionam corretamente contra o
    PostgreSQL real. Nenhuma lógica de negócio é testada aqui — isso é
    responsabilidade dos testes unitários dos UseCases.

    Cada teste roda dentro de uma transação que é revertida ao final,
    garantindo isolamento completo entre os testes.
    """

    @pytest.fixture(autouse=True)
    def setup(self, session) -> None:
        """Inicializa o repositório com a sessão de teste injetada."""
        self.repository = UserSQLAlchemyRepository(session=session)
        self.session = session

    # ─── find_by_email ───────────────────────────────────────────────────────

    async def test_find_by_email_returns_user_when_exists(self) -> None:
        """Usuário persistido → find_by_email retorna a entidade correta."""
        model = await UserFactory.create(self.session, email="ana@example.com")

        result = await self.repository.find_by_email("ana@example.com")

        assert result is not None
        assert result.email == "ana@example.com"
        assert result.id == model.id

    async def test_find_by_email_returns_none_when_not_exists(self) -> None:
        """Email não cadastrado → find_by_email retorna None."""
        result = await self.repository.find_by_email("naoexiste@example.com")

        assert result is None

    # ─── find_by_id ──────────────────────────────────────────────────────────

    async def test_find_by_id_returns_user_when_exists(self) -> None:
        """Usuário persistido → find_by_id retorna a entidade correta."""
        model = await UserFactory.create(self.session)

        result = await self.repository.find_by_id(model.id)

        assert result is not None
        assert result.id == model.id
        assert result.email == model.email

    async def test_find_by_id_returns_none_when_not_exists(self) -> None:
        """ID inexistente → find_by_id retorna None."""
        result = await self.repository.find_by_id(uuid.uuid4())

        assert result is None

    # ─── save ────────────────────────────────────────────────────────────────

    async def test_save_persists_user_and_returns_entity(self) -> None:
        """save() persiste o usuário no banco e retorna a entidade com todos os campos."""
        user = UserFactory.make(email="novo@example.com")

        saved = await self.repository.save(user)

        # O retorno da entidade contém os campos corretos
        assert saved.id == user.id
        assert saved.email == "novo@example.com"
        assert saved.name == user.name

        # Buscar do banco confirma que foi persistido de verdade
        found = await self.repository.find_by_id(user.id)
        assert found is not None
        assert found.email == "novo@example.com"

    # ─── constraint ──────────────────────────────────────────────────────────

    async def test_save_raises_on_duplicate_email(self) -> None:
        """Dois usuários com o mesmo email violam a constraint UNIQUE → IntegrityError."""
        await UserFactory.create(self.session, email="duplicado@example.com")

        user_duplicado = UserFactory.make(email="duplicado@example.com")

        with pytest.raises(IntegrityError):
            await self.repository.save(user_duplicado)
