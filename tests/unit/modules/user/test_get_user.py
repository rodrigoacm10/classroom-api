import uuid

import pytest

from modules.user.application.use_cases.get_user import GetUserUseCase
from tests.factories.user_factory import UserFactory
from tests.unit.fakes.fake_user_repository import FakeUserRepository


class TestGetUserUseCase:
    async def test_get_user_by_id_successfully(self) -> None:
        repo = FakeUserRepository()
        user = UserFactory.make(name="Ana Silva", email="ana.silva@exemplo.com")
        repo.seed(user)

        use_case = GetUserUseCase(repository=repo)
        result = await use_case.execute(user.id)

        assert result.id == user.id
        assert result.name == "Ana Silva"
        assert result.email == "ana.silva@exemplo.com"

    async def test_get_user_not_found_raises_value_error(self) -> None:
        repo = FakeUserRepository()
        use_case = GetUserUseCase(repository=repo)

        random_id = uuid.uuid4()
        with pytest.raises(ValueError, match="Usuário não encontrado."):
            await use_case.execute(random_id)
