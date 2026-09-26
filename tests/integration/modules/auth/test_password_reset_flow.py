import json
from unittest.mock import patch
import pytest

from infra.cache.redis_client import redis_client
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
from modules.user.infra.repositories.user_sqlalchemy_repository import (
    UserSQLAlchemyRepository,
)
from security.password import hash_password, verify_password
from shared.exceptions import BusinessRuleException
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestPasswordResetIntegrationFlow:
    """
    Testes de integração para o fluxo de recuperação de senha (Abordagem B).
    Valida a integração entre os UseCases, o repositório PostgreSQL real e o Redis real.
    """

    @pytest.fixture(autouse=True)
    def setup(self, session) -> None:
        self.session = session
        self.user_repo = UserSQLAlchemyRepository(session=session)
        self.forgot_use_case = ForgotPasswordUseCase(user_repo=self.user_repo, redis=redis_client)
        self.verify_use_case = VerifyResetCodeUseCase(redis=redis_client)
        self.reset_use_case = ResetPasswordUseCase(user_repo=self.user_repo, redis=redis_client)

    async def test_full_password_reset_lifecycle_with_db_and_redis(self) -> None:
        """
        Ciclo completo (Abordagem B):
        1. Usuário solicita código -> salvo no Redis e e-mail disparado.
        2. Usuário valida código -> OTP destruído do Redis e reset_token retornado.
        3. Usuário define nova senha -> senha atualizada no banco, reset_token entra na blacklist.
        4. Reutilização do reset_token é bloqueada.
        """
        email = "aluno.recupera@integracao.com"
        user = await UserFactory.create(
            self.session,
            email=email,
            password_hash=hash_password("SenhaAntiga123"),
        )

        # ── Etapa 1: Solicitar código ──
        with patch("modules.auth.application.use_cases.forgot_password.send_password_reset_email") as mock_email:
            await self.forgot_use_case.execute(ForgotPasswordInput(email=email))

        mock_email.assert_called_once()
        redis_key = f"password_reset:{email}"
        stored_raw = await redis_client.get(redis_key)
        assert stored_raw is not None
        stored_data = json.loads(stored_raw)
        code = stored_data["code"]
        assert len(code) == 6

        # ── Etapa 2: Validar código e obter reset_token ──
        verify_output = await self.verify_use_case.execute(
            VerifyResetCodeInput(email=email, code=code)
        )
        assert verify_output.reset_token is not None
        assert verify_output.token_type == "Bearer"

        # OTP foi removido do Redis no sucesso da validação
        assert await redis_client.get(redis_key) is None

        # ── Etapa 3: Cadastrar nova senha ──
        await self.reset_use_case.execute(
            ResetPasswordInput(
                reset_token=verify_output.reset_token,
                new_password="NovaSenhaSegura@2026",
            )
        )

        # Valida que a senha foi atualizada no banco de dados
        updated_user = await self.user_repo.find_by_id(user.id)
        assert updated_user is not None
        assert verify_password("NovaSenhaSegura@2026", updated_user.password_hash) is True
        assert verify_password("SenhaAntiga123", updated_user.password_hash) is False

        # ── Etapa 4: Reutilização do token é bloqueada ──
        with pytest.raises(BusinessRuleException, match="já utilizado"):
            await self.reset_use_case.execute(
                ResetPasswordInput(
                    reset_token=verify_output.reset_token,
                    new_password="OutraTentativa123",
                )
            )

    async def test_verify_code_wrong_attempts_counter_in_redis(self) -> None:
        """Tentativas incorretas no Redis real são contabilizadas e bloqueiam após 5 erros."""
        email = "tentativas@integracao.com"
        user = await UserFactory.create(self.session, email=email)

        redis_key = f"password_reset:{email}"
        payload = json.dumps({"code": "123456", "user_id": str(user.id), "attempts": 0})
        await redis_client.set(redis_key, payload, ex=900)

        # 1ª tentativa errada
        with pytest.raises(BusinessRuleException, match="Código de recuperação incorreto"):
            await self.verify_use_case.execute(VerifyResetCodeInput(email=email, code="000000"))

        stored_val = await redis_client.get(redis_key)
        assert stored_val is not None
        data = json.loads(stored_val)
        assert data["attempts"] == 1

        # Simula que já estava com 4 tentativas
        data["attempts"] = 4
        await redis_client.set(redis_key, json.dumps(data), ex=900)

        # 5ª tentativa errada -> chave eliminada do Redis
        with pytest.raises(BusinessRuleException, match="Limite de tentativas excedido"):
            await self.verify_use_case.execute(VerifyResetCodeInput(email=email, code="000000"))

        assert await redis_client.get(redis_key) is None
