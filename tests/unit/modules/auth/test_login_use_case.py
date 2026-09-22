import pytest

from modules.auth.application.use_cases.login import LoginInput, LoginUseCase
from tests.factories.user_factory import UserFactory
from tests.unit.fakes.fake_user_repository import FakeUserRepository


class TestLoginUseCase:
    """Testes unitários para LoginUseCase.

    Regras validadas:
    - Credenciais válidas → retorna access_token e refresh_token
    - Usuário não encontrado → ValueError
    - Senha incorreta → ValueError (mesma mensagem — segurança contra enumeração)
    """

    def setup_method(self) -> None:
        self.repo = FakeUserRepository()
        self.use_case = LoginUseCase(repository=self.repo)

    async def test_login_returns_tokens_on_valid_credentials(self) -> None:
        """Usuário existe e senha correta → output contém access_token e refresh_token."""
        plain = "senha_correta"
        user = UserFactory.make_with_password(plain, email="ana@example.com")
        self.repo.seed(user)

        result = await self.use_case.execute(
            LoginInput(email="ana@example.com", password=plain)
        )

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"

    async def test_login_raises_when_user_not_found(self) -> None:
        """Email não cadastrado → ValueError com mensagem de credenciais inválidas."""
        with pytest.raises(ValueError, match="Credenciais inválidas"):
            await self.use_case.execute(
                LoginInput(email="naoexiste@example.com", password="qualquer")
            )

    async def test_login_raises_when_password_is_wrong(self) -> None:
        """Usuário existe mas senha errada → ValueError (sem revelar qual campo falhou)."""
        user = UserFactory.make_with_password("senha_certa", email="bob@example.com")
        self.repo.seed(user)

        with pytest.raises(ValueError, match="Credenciais inválidas"):
            await self.use_case.execute(
                LoginInput(email="bob@example.com", password="senha_errada")
            )
