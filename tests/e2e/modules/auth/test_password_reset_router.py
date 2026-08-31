import json
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from infra.cache.redis_client import redis_client
from security.password import hash_password
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestForgotPasswordEndpoint:
    """Testes E2E para POST /auth/forgot-password"""

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
class TestResetPasswordEndpoint:
    """Testes E2E para POST /auth/reset-password"""

    async def test_reset_password_success_allows_new_login_and_invalidates_old_sessions(
        self, client: AsyncClient, session
    ) -> None:
        """Fluxo completo: reseta senha, permite login com a nova senha e invalida token antigo."""
        user = await UserFactory.create(
            session,
            email="reset_completo@e2e.com",
            password_hash=hash_password("SenhaAntiga123!"),
        )

        # 1. Faz login prévio para obter um token que deve ser invalidado
        login_res = await client.post(
            "/auth/login",
            json={"email": "reset_completo@e2e.com", "password": "SenhaAntiga123!", "client_type": "mobile"},
        )
        assert login_res.status_code == 200
        old_access_token = login_res.json()["access_token"]

        # 2. Configura código no Redis
        code = "654321"
        payload = json.dumps({"code": code, "user_id": str(user.id), "attempts": 0})
        await redis_client.set("password_reset:reset_completo@e2e.com", payload, ex=900)

        # 3. Executa redefinição de senha
        reset_res = await client.post(
            "/auth/reset-password",
            json={
                "email": "reset_completo@e2e.com",
                "code": code,
                "new_password": "NovaSenhaForte2026!",
            },
        )
        assert reset_res.status_code == 200
        assert "Senha redefinida com sucesso" in reset_res.json()["message"]

        # 4. Código foi consumido (não está mais no Redis)
        assert await redis_client.get("password_reset:reset_completo@e2e.com") is None

        # 5. Tentativa de login com senha antiga deve falhar (401)
        old_login_res = await client.post(
            "/auth/login",
            json={"email": "reset_completo@e2e.com", "password": "SenhaAntiga123!", "client_type": "mobile"},
        )
        assert old_login_res.status_code == 401

        # 6. Login com nova senha deve funcionar (200)
        new_login_res = await client.post(
            "/auth/login",
            json={"email": "reset_completo@e2e.com", "password": "NovaSenhaForte2026!", "client_type": "mobile"},
        )
        assert new_login_res.status_code == 200

        # 7. Token antigo emitido antes do reset é rejeitado com 401 (sessão encerrada)
        revoked_check_res = await client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {old_access_token}"},
        )
        assert revoked_check_res.status_code == 401
        assert "alteração de senha" in revoked_check_res.json()["detail"]

    async def test_reset_password_wrong_code_returns_400(
        self, client: AsyncClient, session
    ) -> None:
        """Código de recuperação incorreto -> 400 Bad Request."""
        user = await UserFactory.create(session, email="codigo_errado@e2e.com")

        payload = json.dumps({"code": "123456", "user_id": str(user.id), "attempts": 0})
        await redis_client.set("password_reset:codigo_errado@e2e.com", payload, ex=900)

        response = await client.post(
            "/auth/reset-password",
            json={
                "email": "codigo_errado@e2e.com",
                "code": "999999",
                "new_password": "NovaSenhaForte123",
            },
        )
        assert response.status_code == 400
        assert "Código de recuperação incorreto" in response.json()["detail"]

    async def test_reset_password_expired_or_not_requested_returns_400(
        self, client: AsyncClient, session
    ) -> None:
        """Tentativa de reset sem código ativo no Redis -> 400 Bad Request."""
        response = await client.post(
            "/auth/reset-password",
            json={
                "email": "nao_solicitou@e2e.com",
                "code": "123456",
                "new_password": "NovaSenhaForte123",
            },
        )
        assert response.status_code == 400
        assert "Código de recuperação inválido ou expirado" in response.json()["detail"]

    async def test_reset_password_short_password_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Nova senha com menos de 6 caracteres -> 422 Unprocessable Entity."""
        response = await client.post(
            "/auth/reset-password",
            json={
                "email": "qualquer@e2e.com",
                "code": "123456",
                "new_password": "123",
            },
        )
        assert response.status_code == 422

    async def test_reset_password_invalid_code_format_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Código que não seja exatamente 6 dígitos numéricos -> 422 Unprocessable Entity."""
        response = await client.post(
            "/auth/reset-password",
            json={
                "email": "qualquer@e2e.com",
                "code": "ABC123",
                "new_password": "NovaSenhaForte123",
            },
        )
        assert response.status_code == 422
