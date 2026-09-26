import json
from unittest.mock import patch
from uuid import uuid4

import pytest

from modules.auth.application.use_cases.forgot_password import (
    ForgotPasswordInput,
    ForgotPasswordUseCase,
)
from modules.auth.application.use_cases.reset_password import (
    ResetPasswordInput,
    ResetPasswordUseCase,
)
from modules.auth.application.use_cases.verify_reset_code import (
    VerifyResetCodeInput,
    VerifyResetCodeUseCase,
)
from security.jwt import (
    create_access_token,
    create_reset_password_token,
    decode_reset_password_token,
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
class TestVerifyResetCodeUseCase:
    """Testes unitários para VerifyResetCodeUseCase (Abordagem B)."""

    def setup_method(self) -> None:
        self.redis = FakeRedis()
        self.use_case = VerifyResetCodeUseCase(redis=self.redis)

    async def test_verify_code_success_destroys_otp_and_returns_reset_token(self) -> None:
        """Código correto -> destrói OTP do Redis e retorna reset_token JWT válido."""
        user_id = uuid4()
        payload = json.dumps({"code": "847291", "user_id": str(user_id), "attempts": 0})
        await self.redis.set("password_reset:aluno@escola.com", payload, ex=900)

        result = await self.use_case.execute(
            VerifyResetCodeInput(email="aluno@escola.com", code="847291")
        )

        # 1. Retorno contém token e metadados
        assert result.reset_token is not None
        assert result.token_type == "Bearer"
        assert result.expires_in == 600

        # 2. Token gerado é válido e contém os dados corretos
        decoded = decode_reset_password_token(result.reset_token)
        assert decoded["sub"] == str(user_id)
        assert decoded["type"] == "password_reset"
        assert "jti" in decoded

        # 3. OTP foi DESTRUÍDO no Redis (uso único)
        stored = await self.redis.get("password_reset:aluno@escola.com")
        assert stored is None

    async def test_verify_code_expired_or_not_found_raises_business_rule_exception(self) -> None:
        """Chave inexistente ou expirada -> lança BusinessRuleException."""
        with pytest.raises(BusinessRuleException, match="inválido ou expirado"):
            await self.use_case.execute(
                VerifyResetCodeInput(email="desconhecido@escola.com", code="123456")
            )

    async def test_verify_code_wrong_code_increments_attempts(self) -> None:
        """Código incorreto -> incrementa attempts no Redis e lança BusinessRuleException."""
        payload = json.dumps({"code": "123456", "user_id": "some-id", "attempts": 1})
        await self.redis.set("password_reset:aluno@escola.com", payload, ex=900)

        with pytest.raises(BusinessRuleException, match="Código de recuperação incorreto"):
            await self.use_case.execute(
                VerifyResetCodeInput(email="aluno@escola.com", code="999999")
            )

        stored_raw = await self.redis.get("password_reset:aluno@escola.com")
        assert stored_raw is not None
        stored = json.loads(stored_raw)
        assert stored["attempts"] == 2

    async def test_verify_code_exceeds_5_attempts_destroys_key(self) -> None:
        """Ao atingir 5 tentativas -> chave é deletada do Redis (anti-brute-force)."""
        payload = json.dumps({"code": "123456", "user_id": "some-id", "attempts": 4})
        await self.redis.set("password_reset:aluno@escola.com", payload, ex=900)

        with pytest.raises(BusinessRuleException, match="Limite de tentativas excedido"):
            await self.use_case.execute(
                VerifyResetCodeInput(email="aluno@escola.com", code="999999")
            )

        assert await self.redis.get("password_reset:aluno@escola.com") is None


@pytest.mark.asyncio
class TestResetPasswordUseCase:
    """Testes unitários para ResetPasswordUseCase (Abordagem B)."""

    def setup_method(self) -> None:
        self.user_repo = FakeUserRepository()
        self.redis = FakeRedis()
        self.use_case = ResetPasswordUseCase(user_repo=self.user_repo, redis=self.redis)

    async def test_reset_password_success(self) -> None:
        """Token válido -> atualiza senha, adiciona JTI à blacklist e revoga sessões antigas."""
        user = UserFactory.make(
            email="aluno@escola.com",
            password_hash=hash_password("AntigaSenha123"),
        )
        self.user_repo.seed(user)

        # Gera token JWT temporário de redefinição
        reset_token = create_reset_password_token(user.id)
        decoded = decode_reset_password_token(reset_token)
        jti = decoded["jti"]

        with patch("modules.auth.application.use_cases.reset_password.revoke_user_sessions") as mock_revoke:
            await self.use_case.execute(
                ResetPasswordInput(
                    reset_token=reset_token,
                    new_password="NovaSenhaForte@2026",
                )
            )

        # 1. Senha do usuário foi alterada
        updated_user = await self.user_repo.find_by_id(user.id)
        assert updated_user is not None
        assert verify_password("NovaSenhaForte@2026", updated_user.password_hash) is True

        # 2. Token foi colocado na blacklist do Redis (single-use)
        blacklisted = await self.redis.get(f"blacklist:{jti}")
        assert blacklisted == "revoked"

        # 3. Sessões anteriores foram invalidadas
        mock_revoke.assert_called_once()
        assert mock_revoke.call_args[0][0] == user.id

    async def test_reset_password_token_reuse_fails(self) -> None:
        """Tentativa de reutilizar o mesmo reset_token -> rejeitado com BusinessRuleException."""
        user = UserFactory.make(email="aluno@escola.com")
        self.user_repo.seed(user)

        reset_token = create_reset_password_token(user.id)

        with patch("modules.auth.application.use_cases.reset_password.revoke_user_sessions"):
            await self.use_case.execute(
                ResetPasswordInput(
                    reset_token=reset_token,
                    new_password="NovaSenhaForte@2026",
                )
            )

        # Segunda chamada com o mesmo token deve falhar
        with pytest.raises(BusinessRuleException, match="já utilizado"):
            await self.use_case.execute(
                ResetPasswordInput(
                    reset_token=reset_token,
                    new_password="OutraSenhaQualquer123",
                )
            )

    async def test_reset_password_expired_token_raises_business_rule_exception(self) -> None:
        """Token expirado -> lança BusinessRuleException."""
        user_id = uuid4()
        # Gera token já expirado (delta negativo)
        expired_token = create_reset_password_token(user_id, expire_minutes=-5)

        with pytest.raises(BusinessRuleException, match="expirado"):
            await self.use_case.execute(
                ResetPasswordInput(
                    reset_token=expired_token,
                    new_password="NovaSenha123",
                )
            )

    async def test_reset_password_invalid_token_signature_raises_business_rule_exception(self) -> None:
        """Token malformado ou com assinatura inválida -> lança BusinessRuleException."""
        with pytest.raises(BusinessRuleException, match="Token de recuperação inválido"):
            await self.use_case.execute(
                ResetPasswordInput(
                    reset_token="token.completamente.invalido",
                    new_password="NovaSenha123",
                )
            )

    async def test_reset_password_wrong_token_type_raises_business_rule_exception(self) -> None:
        """Token do tipo access em vez de password_reset -> rejeitado como inválido."""
        user_id = uuid4()
        access_token = create_access_token(user_id=user_id)

        with pytest.raises(BusinessRuleException, match="Token de recuperação inválido"):
            await self.use_case.execute(
                ResetPasswordInput(
                    reset_token=access_token,
                    new_password="NovaSenha123",
                )
            )

    async def test_reset_password_short_password_raises_business_rule_exception(self) -> None:
        """Senha com menos de 6 caracteres -> lança BusinessRuleException sem decodificar o token."""
        with pytest.raises(BusinessRuleException, match="mínimo 6 caracteres"):
            await self.use_case.execute(
                ResetPasswordInput(
                    reset_token="qualquer-token",
                    new_password="123",
                )
            )

    async def test_reset_password_user_deleted_raises_resource_not_found(self) -> None:
        """Se o usuário foi removido da base antes de usar o token -> ResourceNotFoundException."""
        user_id = uuid4()
        reset_token = create_reset_password_token(user_id)

        with pytest.raises(ResourceNotFoundException, match="Usuário não encontrado"):
            await self.use_case.execute(
                ResetPasswordInput(
                    reset_token=reset_token,
                    new_password="NovaSenha123",
                )
            )
