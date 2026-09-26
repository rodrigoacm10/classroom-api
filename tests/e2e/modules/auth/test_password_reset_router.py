import json
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from infra.cache.redis_client import redis_client
from security.jwt import create_reset_password_token
from security.password import hash_password
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestForgotPasswordEndpoint:
    """Testes E2E para POST /auth/forgot-password (Etapa 1)."""

    async def test_forgot_password_registered_email_returns_200(
        self, client: AsyncClient, session
    ) -> None:
        """Usuário existente -> retorna 200, armazena OTP no Redis e envia e-mail."""
        user = await UserFactory.create(
            session,
            email="recuperar_sucesso@e2e.com",
            name="Aluno Recuperacao",
        )

        with patch("modules.auth.application.use_cases.forgot_password.send_password_reset_email") as mock_email:
            response = await client.post(
                "/auth/forgot-password",
                json={"email": "recuperar_sucesso@e2e.com"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "código de recuperação" in data["message"]

        # Verifica se o código foi gravado no Redis real de testes
        stored_raw = await redis_client.get("password_reset:recuperar_sucesso@e2e.com")
        assert stored_raw is not None
        payload = json.loads(stored_raw)
        assert len(payload["code"]) == 6
        assert payload["user_id"] == str(user.id)

        mock_email.assert_called_once()

    async def test_forgot_password_unregistered_email_returns_200_identically(
        self, client: AsyncClient, session
    ) -> None:
        """E-mail inexistente -> retorna exatamente 200 com a mesma mensagem (anti-enumeração)."""
        with patch("modules.auth.application.use_cases.forgot_password.send_password_reset_email") as mock_email:
            response = await client.post(
                "/auth/forgot-password",
                json={"email": "inexistente@e2e.com"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "código de recuperação" in data["message"]

        # Nada deve ser gravado no Redis
        assert await redis_client.get("password_reset:inexistente@e2e.com") is None
        mock_email.assert_not_called()

    async def test_forgot_password_invalid_email_format_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Formato de e-mail inválido -> 422 Unprocessable Entity."""
        response = await client.post(
            "/auth/forgot-password",
            json={"email": "formato-invalido"},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestVerifyResetCodeEndpoint:
    """Testes E2E para POST /auth/verify-reset-code (Etapa 2 - Abordagem B)."""

    async def test_verify_reset_code_success_returns_token_and_destroys_otp(
        self, client: AsyncClient, session
    ) -> None:
        """Código correto -> 200 com reset_token e destrói o OTP no Redis."""
        email = "verify_sucesso@e2e.com"
        user = await UserFactory.create(session, email=email)

        code = "123456"
        payload = json.dumps({"code": code, "user_id": str(user.id), "attempts": 0})
        await redis_client.set(f"password_reset:{email}", payload, ex=900)

        response = await client.post(
            "/auth/verify-reset-code",
            json={"email": email, "code": code},
        )

        assert response.status_code == 200
        body = response.json()
        assert "reset_token" in body
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] == 600

        # OTP foi destruído no Redis imediatamente
        assert await redis_client.get(f"password_reset:{email}") is None

    async def test_verify_reset_code_wrong_code_returns_400(
        self, client: AsyncClient, session
    ) -> None:
        """Código incorreto -> 400 Bad Request e preserva chave com attempts incrementado."""
        email = "verify_errado@e2e.com"
        user = await UserFactory.create(session, email=email)

        payload = json.dumps({"code": "123456", "user_id": str(user.id), "attempts": 0})
        await redis_client.set(f"password_reset:{email}", payload, ex=900)

        response = await client.post(
            "/auth/verify-reset-code",
            json={"email": email, "code": "999999"},
        )

        assert response.status_code == 400
        assert "Código de recuperação incorreto" in response.json()["detail"]

        stored_raw = await redis_client.get(f"password_reset:{email}")
        assert stored_raw is not None
        stored = json.loads(stored_raw)
        assert stored["attempts"] == 1

    async def test_verify_reset_code_exceeds_5_attempts_destroys_key(
        self, client: AsyncClient, session
    ) -> None:
        """5 tentativas incorretas -> destrói chave no Redis e retorna 400."""
        email = "verify_limite@e2e.com"
        user = await UserFactory.create(session, email=email)

        payload = json.dumps({"code": "123456", "user_id": str(user.id), "attempts": 4})
        await redis_client.set(f"password_reset:{email}", payload, ex=900)

        response = await client.post(
            "/auth/verify-reset-code",
            json={"email": email, "code": "999999"},
        )

        assert response.status_code == 400
        assert "Limite de tentativas excedido" in response.json()["detail"]
        assert await redis_client.get(f"password_reset:{email}") is None

    async def test_verify_reset_code_invalid_format_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Código com formato inválido (ex: letras ou tamanho diferente de 6) -> 422."""
        response = await client.post(
            "/auth/verify-reset-code",
            json={"email": "teste@e2e.com", "code": "ABC12"},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestResetPasswordEndpoint:
    """Testes E2E para POST /auth/reset-password (Etapa 3 - Abordagem B)."""

    async def test_reset_password_full_flow_success(
        self, client: AsyncClient, session
    ) -> None:
        """Fluxo completo E2E: forgot -> verify -> reset -> login com nova senha."""
        email = "fluxo_completo_b@e2e.com"
        await UserFactory.create(
            session,
            email=email,
            password_hash=hash_password("SenhaAntiga123!"),
        )

        # 1. Faz login prévio para obter token
        login_res = await client.post(
            "/auth/login",
            json={"email": email, "password": "SenhaAntiga123!", "client_type": "mobile"},
        )
        assert login_res.status_code == 200
        old_access_token = login_res.json()["access_token"]

        # 2. Solicita código
        with patch("modules.auth.application.use_cases.forgot_password.send_password_reset_email"):
            forgot_res = await client.post("/auth/forgot-password", json={"email": email})
        assert forgot_res.status_code == 200

        # 3. Lê código do Redis
        stored_raw = await redis_client.get(f"password_reset:{email}")
        assert stored_raw is not None
        code = json.loads(stored_raw)["code"]

        # 4. Valida código e obtém reset_token (Etapa 2)
        verify_res = await client.post(
            "/auth/verify-reset-code",
            json={"email": email, "code": code},
        )
        assert verify_res.status_code == 200
        reset_token = verify_res.json()["reset_token"]

        # 5. Redefine senha utilizando o reset_token (Etapa 3)
        reset_res = await client.post(
            "/auth/reset-password",
            json={
                "reset_token": reset_token,
                "new_password": "NovaSenhaForte2026!",
            },
        )
        assert reset_res.status_code == 200
        assert "Senha redefinida com sucesso" in reset_res.json()["message"]

        # 6. Tentativa de login com senha antiga deve falhar (401)
        old_login_res = await client.post(
            "/auth/login",
            json={"email": email, "password": "SenhaAntiga123!", "client_type": "mobile"},
        )
        assert old_login_res.status_code == 401

        # 7. Login com nova senha deve funcionar (200)
        new_login_res = await client.post(
            "/auth/login",
            json={"email": email, "password": "NovaSenhaForte2026!", "client_type": "mobile"},
        )
        assert new_login_res.status_code == 200

        # 8. Token antigo foi revogado (401 ao tentar usar)
        revoked_check_res = await client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {old_access_token}"},
        )
        assert revoked_check_res.status_code == 401

    async def test_reset_password_cannot_reuse_reset_token(
        self, client: AsyncClient, session
    ) -> None:
        """Tentativa de reutilizar o mesmo reset_token -> 400 Bad Request."""
        email = "reuso_token@e2e.com"
        user = await UserFactory.create(session, email=email)
        reset_token = create_reset_password_token(user.id)

        # 1ª vez: sucesso
        res1 = await client.post(
            "/auth/reset-password",
            json={"reset_token": reset_token, "new_password": "NovaSenhaForte123"},
        )
        assert res1.status_code == 200

        # 2ª vez com o mesmo token: falha
        res2 = await client.post(
            "/auth/reset-password",
            json={"reset_token": reset_token, "new_password": "OutraSenhaQualquer"},
        )
        assert res2.status_code == 400
        assert "já utilizado" in res2.json()["detail"]

    async def test_reset_password_expired_token_returns_400(
        self, client: AsyncClient, session
    ) -> None:
        """Token de recuperação expirado -> 400 Bad Request."""
        expired_token = create_reset_password_token(uuid4(), expire_minutes=-5)
        response = await client.post(
            "/auth/reset-password",
            json={"reset_token": expired_token, "new_password": "NovaSenhaForte123"},
        )
        assert response.status_code == 400
        assert "expirado" in response.json()["detail"]

    async def test_reset_password_invalid_token_returns_400(
        self, client: AsyncClient, session
    ) -> None:
        """Token com assinatura inválida ou adulterado -> 400 Bad Request."""
        response = await client.post(
            "/auth/reset-password",
            json={"reset_token": "token.jwt.falso", "new_password": "NovaSenhaForte123"},
        )
        assert response.status_code == 400
        assert "Token de recuperação inválido" in response.json()["detail"]

    async def test_reset_password_short_password_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Nova senha com menos de 6 caracteres -> 422 Unprocessable Entity."""
        response = await client.post(
            "/auth/reset-password",
            json={"reset_token": "qualquer_token", "new_password": "123"},
        )
        assert response.status_code == 422
