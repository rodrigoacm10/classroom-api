import json
from unittest.mock import patch

import pytest

from modules.auth.application.use_cases.forgot_password import (
    ForgotPasswordInput,
    ForgotPasswordUseCase,
)
from modules.auth.application.use_cases.reset_password import (
    ResetPasswordInput,
    ResetPasswordUseCase,
)
from security.password import hash_password, verify_password
from shared.exceptions import BusinessRuleException, ResourceNotFoundException
from tests.factories.user_factory import UserFactory
from tests.unit.fakes.fake_user_repository import FakeUserRepository


class FakeRedis:
    """Implementação em memória do Redis para testes unitários isolados."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value
        if ex:
            self.ttls[key] = ex

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)
        self.ttls.pop(key, None)

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, 900)


@pytest.mark.asyncio
class TestForgotPasswordUseCase:
    """Testes unitários para ForgotPasswordUseCase."""

    def setup_method(self) -> None:
        self.user_repo = FakeUserRepository()
        self.redis = FakeRedis()
        self.use_case = ForgotPasswordUseCase(user_repo=self.user_repo, redis=self.redis)

    async def test_forgot_password_success_generates_code_and_stores_in_redis(self) -> None:
        """Usuário existente -> gera código de 6 dígitos no Redis e dispara envio de e-mail."""
        user = UserFactory.make(email="aluno@escola.com", name="Aluno Teste")
        self.user_repo.seed(user)

        with patch("modules.auth.application.use_cases.forgot_password.send_password_reset_email") as mock_email:
            await self.use_case.execute(ForgotPasswordInput(email="aluno@escola.com"))

        stored_raw = await self.redis.get("password_reset:aluno@escola.com")
        assert stored_raw is not None

        payload = json.loads(stored_raw)
        assert len(payload["code"]) == 6
        assert payload["code"].isdigit()
        assert payload["user_id"] == str(user.id)
        assert payload["attempts"] == 0

        mock_email.assert_called_once()
        call_kwargs = mock_email.call_args.kwargs
        assert call_kwargs["to_email"] == "aluno@escola.com"
        assert call_kwargs["code"] == payload["code"]
        assert call_kwargs["user_name"] == "Aluno Teste"

    async def test_forgot_password_unknown_email_silently_returns_without_error(self) -> None:
        """E-mail não cadastrado -> não lança exceção, não armazena no Redis e não dispara e-mail."""
        with patch("modules.auth.application.use_cases.forgot_password.send_password_reset_email") as mock_email:
            await self.use_case.execute(ForgotPasswordInput(email="fantasma@escola.com"))

        stored = await self.redis.get("password_reset:fantasma@escola.com")
        assert stored is None
        mock_email.assert_not_called()


@pytest.mark.asyncio
class TestResetPasswordUseCase:
    """Testes unitários para ResetPasswordUseCase."""

    def setup_method(self) -> None:
        self.user_repo = FakeUserRepository()
        self.redis = FakeRedis()
        self.use_case = ResetPasswordUseCase(user_repo=self.user_repo, redis=self.redis)

    async def test_reset_password_success(self) -> None:
        """Código correto -> atualiza senha, deleta chave de reset e invalida sessões no Redis."""
        user = UserFactory.make(
            email="aluno@escola.com",
            password_hash=hash_password("AntigaSenha123"),
        )
        self.user_repo.seed(user)

        # Simula código armazenado no Redis
        code = "749201"
        payload = json.dumps({"code": code, "user_id": str(user.id), "attempts": 0})
        await self.redis.set("password_reset:aluno@escola.com", payload, ex=900)

        with patch("modules.auth.application.use_cases.reset_password.revoke_user_sessions") as mock_revoke:
            await self.use_case.execute(
                ResetPasswordInput(
                    email="aluno@escola.com",
                    code=code,
                    new_password="NovaSenhaForte@2026",
                )
            )

        # 1. Senha do usuário foi alterada
        updated_user = await self.user_repo.find_by_id(user.id)
        assert updated_user is not None
        assert verify_password("NovaSenhaForte@2026", updated_user.password_hash) is True

        # 2. Código foi deletado do Redis (single-use)
        assert await self.redis.get("password_reset:aluno@escola.com") is None

        # 3. Sessões anteriores foram invalidadas
        mock_revoke.assert_called_once()
        assert mock_revoke.call_args[0][0] == user.id

    async def test_reset_password_invalid_or_expired_code_raises_business_rule_exception(self) -> None:
        """Sem registro no Redis (código expirado ou não solicitado) -> lança BusinessRuleException."""
        with pytest.raises(BusinessRuleException, match="Código de recuperação inválido ou expirado"):
            await self.use_case.execute(
                ResetPasswordInput(
                    email="aluno@escola.com",
                    code="123456",
                    new_password="NovaSenha123",
                )
            )

    async def test_reset_password_wrong_code_increments_attempts(self) -> None:
        """Código incorreto com menos de 5 tentativas -> incrementa tentativas e lança exceção."""
        user = UserFactory.make(email="aluno@escola.com")
        self.user_repo.seed(user)

        payload = json.dumps({"code": "111111", "user_id": str(user.id), "attempts": 0})
        await self.redis.set("password_reset:aluno@escola.com", payload, ex=900)

        with pytest.raises(BusinessRuleException, match="Código de recuperação incorreto"):
            await self.use_case.execute(
                ResetPasswordInput(
                    email="aluno@escola.com",
                    code="999999",
                    new_password="NovaSenha123",
                )
            )

        stored_raw = await self.redis.get("password_reset:aluno@escola.com")
        assert stored_raw is not None
        data = json.loads(stored_raw)
        assert data["attempts"] == 1

    async def test_reset_password_exceeds_5_attempts_destroys_key(self) -> None:
        """5ª tentativa incorreta -> destrói a chave no Redis e bloqueia o reset."""
        user = UserFactory.make(email="aluno@escola.com")
        self.user_repo.seed(user)

        payload = json.dumps({"code": "111111", "user_id": str(user.id), "attempts": 4})
        await self.redis.set("password_reset:aluno@escola.com", payload, ex=900)

        with pytest.raises(BusinessRuleException, match="Limite de tentativas excedido"):
            await self.use_case.execute(
                ResetPasswordInput(
                    email="aluno@escola.com",
                    code="999999",
                    new_password="NovaSenha123",
                )
            )

        # Chave foi deletada do Redis
        assert await self.redis.get("password_reset:aluno@escola.com") is None

    async def test_reset_password_short_password_raises_business_rule_exception(self) -> None:
        """Senha com menos de 6 caracteres -> lança BusinessRuleException sem consultar Redis."""
        with pytest.raises(BusinessRuleException, match="mínimo 6 caracteres"):
            await self.use_case.execute(
                ResetPasswordInput(
                    email="aluno@escola.com",
                    code="123456",
                    new_password="123",
                )
            )

    async def test_reset_password_user_deleted_raises_resource_not_found(self) -> None:
        """Se o usuário foi removido da base antes de usar o código -> ResourceNotFoundException."""
        user = UserFactory.make(email="aluno@escola.com")
        # Note que NÃO damos self.user_repo.seed(user)

        payload = json.dumps({"code": "111111", "user_id": str(user.id), "attempts": 0})
        await self.redis.set("password_reset:aluno@escola.com", payload, ex=900)

        with pytest.raises(ResourceNotFoundException, match="Usuário não encontrado"):
            await self.use_case.execute(
                ResetPasswordInput(
                    email="aluno@escola.com",
                    code="111111",
                    new_password="NovaSenha123",
                )
            )
