import pytest

from modules.user.application.use_cases.create_user import CreateUserInput, CreateUserUseCase
from tests.factories.user_factory import UserFactory
from tests.unit.fakes.fake_user_repository import FakeUserRepository


class TestCreateUserUseCase:
    async def test_create_user_successfully(self) -> None:
        repo = FakeUserRepository()
        use_case = CreateUserUseCase(repository=repo)

        user = await use_case.execute(
            CreateUserInput(
                name="Ana Silva",
                email="ana.silva@exemplo.com",
                password="SecurePassword123!",
            )
        )

        assert user.id is not None
        assert user.name == "Ana Silva"
        assert user.email == "ana.silva@exemplo.com"
        assert user.password_hash != "SecurePassword123!"

    async def test_create_user_with_duplicate_email_raises_value_error(self) -> None:
        repo = FakeUserRepository()
        existing_user = UserFactory.make(email="duplicate@exemplo.com")
        repo.seed(existing_user)

        use_case = CreateUserUseCase(repository=repo)
        with pytest.raises(ValueError, match="E-mail já cadastrado."):
            await use_case.execute(
                CreateUserInput(
                    name="Outro Nome",
                    email="duplicate@exemplo.com",
                    password="AnotherPassword123!",
                )
            )
