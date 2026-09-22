"""
Testes E2E para o módulo Auth.

Cobrem os 4 endpoints do fluxo de autenticação disparando requisições HTTP reais
contra a aplicação FastAPI em memória via httpx.AsyncClient + ASGITransport.

Cada teste:
1. Cria dados no banco de testes via factories (UserFactory.create / TenantFactory.create).
2. Executa requisições HTTP reais ao endpoint testado.
3. Valida status code, body JSON e cookies de resposta.
4. Os dados são desfeitos automaticamente via rollback ao final do teste.
"""
import uuid

import pytest

from security.password import hash_password
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory

# Senha usada em todos os testes que precisam de credenciais válidas
_PLAIN_PASSWORD = "Test@e2e2024"


# ─── Helper ──────────────────────────────────────────────────────────────────

async def _login_mobile(client, email: str, password: str) -> dict:
    """
    Realiza login com client_type=mobile e retorna o dict de tokens.
    Falha o teste imediatamente se o login não retornar 200.
    """
    response = await client.post(
        "/auth/login",
        json={"email": email, "password": password, "client_type": "mobile"},
    )
    assert response.status_code == 200, f"Login helper falhou ({response.status_code}): {response.text}"
    return response.json()


# ─── Login ───────────────────────────────────────────────────────────────────

class TestLoginEndpoint:
    """POST /auth/login"""

    async def test_login_mobile_returns_tokens_in_body(self, client, session) -> None:
        """Credenciais válidas + client_type=mobile → 200 com access_token e refresh_token no body."""
        await UserFactory.create(
            session,
            email="login_mobile@e2e.com",
            password_hash=hash_password(_PLAIN_PASSWORD),
        )

        response = await client.post(
            "/auth/login",
            json={
                "email": "login_mobile@e2e.com",
                "password": _PLAIN_PASSWORD,
                "client_type": "mobile",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_web_returns_access_token_in_body_and_refresh_in_cookie(
        self, client, session
    ) -> None:
        """client_type=web → access_token no body; refresh_token enviado no Cookie HttpOnly."""
        await UserFactory.create(
            session,
            email="login_web@e2e.com",
            password_hash=hash_password(_PLAIN_PASSWORD),
        )

        response = await client.post(
            "/auth/login",
            json={
                "email": "login_web@e2e.com",
                "password": _PLAIN_PASSWORD,
                "client_type": "web",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" not in data       # refresh NÃO deve estar no body
        assert "refresh_token" in response.cookies  # refresh deve estar no cookie

    async def test_login_returns_401_when_user_not_found(self, client, session) -> None:
        """Email não cadastrado → 401 Unauthorized."""
        response = await client.post(
            "/auth/login",
            json={"email": "fantasma@e2e.com", "password": _PLAIN_PASSWORD},
        )

        assert response.status_code == 401

    async def test_login_returns_401_when_password_is_wrong(self, client, session) -> None:
        """Senha incorreta → 401 Unauthorized (sem revelar qual campo falhou)."""
        await UserFactory.create(
            session,
            email="senha_errada@e2e.com",
            password_hash=hash_password(_PLAIN_PASSWORD),
        )

        response = await client.post(
            "/auth/login",
            json={"email": "senha_errada@e2e.com", "password": "senha_incorreta"},
        )

        assert response.status_code == 401

    async def test_login_returns_422_when_email_is_invalid(self, client, session) -> None:
        """Email malformado → 422 Unprocessable Entity (Pydantic rejeita o schema)."""
        response = await client.post(
            "/auth/login",
            json={"email": "isto-nao-e-um-email", "password": _PLAIN_PASSWORD},
        )

        assert response.status_code == 422


# ─── Refresh ─────────────────────────────────────────────────────────────────

class TestRefreshEndpoint:
    """POST /auth/refresh"""

    async def test_refresh_mobile_returns_new_tokens_in_body(
        self, client, session
    ) -> None:
        """refresh_token no body (mobile) → 200 com novos access_token e refresh_token."""
        await UserFactory.create(
            session,
            email="refresh_mobile@e2e.com",
            password_hash=hash_password(_PLAIN_PASSWORD),
        )
        tokens = await _login_mobile(client, "refresh_mobile@e2e.com", _PLAIN_PASSWORD)

        response = await client.post(
            "/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_refresh_web_returns_access_token_and_renews_cookie(
        self, client, session
    ) -> None:
        """
        Cliente web: o AsyncClient envia automaticamente o cookie refresh_token
        obtido no login. O endpoint deve renovar o access_token e o cookie.
        """
        await UserFactory.create(
            session,
            email="refresh_web@e2e.com",
            password_hash=hash_password(_PLAIN_PASSWORD),
        )
        # Login web: o AsyncClient armazena o cookie refresh_token automaticamente
        login_response = await client.post(
            "/auth/login",
            json={
                "email": "refresh_web@e2e.com",
                "password": _PLAIN_PASSWORD,
                "client_type": "web",
            },
        )
        assert login_response.status_code == 200

        # /auth/refresh sem body — o cookie é enviado automaticamente pelo AsyncClient
        response = await client.post("/auth/refresh")

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" not in data           # web: refresh fica no cookie
        assert "refresh_token" in response.cookies   # cookie renovado na resposta

    async def test_refresh_returns_401_when_no_token_provided(
        self, client, session
    ) -> None:
        """Sem body e sem cookie → 401 Unauthorized."""
        response = await client.post("/auth/refresh", json={})

        assert response.status_code == 401

    async def test_refresh_returns_401_with_invalid_token(
        self, client, session
    ) -> None:
        """Token inválido no body → 401 Unauthorized."""
        response = await client.post(
            "/auth/refresh",
            json={"refresh_token": "este.token.e.invalido"},
        )

        assert response.status_code == 401


# ─── Switch Tenant ───────────────────────────────────────────────────────────

class TestSwitchTenantEndpoint:
    """POST /auth/switch-tenant"""

    async def test_switch_tenant_returns_enriched_token(
        self, client, session
    ) -> None:
        """Usuário é membro da tenant → 200 com access_token enriquecido (tenant_id + role)."""
        user = await UserFactory.create(
            session,
            email="switch_member@e2e.com",
            password_hash=hash_password(_PLAIN_PASSWORD),
        )
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id
        )

        tokens = await _login_mobile(client, "switch_member@e2e.com", _PLAIN_PASSWORD)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        response = await client.post(
            "/auth/switch-tenant",
            json={"tenant_id": str(tenant.id)},
            headers=headers,
        )

        assert response.status_code == 200
        assert "access_token" in response.json()

    async def test_switch_tenant_returns_403_when_not_member(
        self, client, session
    ) -> None:
        """Usuário NÃO é membro da tenant → 403 Forbidden."""
        user = await UserFactory.create(
            session,
            email="switch_nomember@e2e.com",
            password_hash=hash_password(_PLAIN_PASSWORD),
        )
        tenant = await TenantFactory.create(session)
        # Nenhuma membership criada!

        tokens = await _login_mobile(client, "switch_nomember@e2e.com", _PLAIN_PASSWORD)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        response = await client.post(
            "/auth/switch-tenant",
            json={"tenant_id": str(tenant.id)},
            headers=headers,
        )

        assert response.status_code == 403

    async def test_switch_tenant_returns_401_without_auth(
        self, client, session
    ) -> None:
        """Sem header Authorization → 401 Unauthorized."""
        response = await client.post(
            "/auth/switch-tenant",
            json={"tenant_id": str(uuid.uuid4())},
        )

        assert response.status_code == 401


# ─── Logout ──────────────────────────────────────────────────────────────────

class TestLogoutEndpoint:
    """POST /auth/logout"""

    async def test_logout_returns_200_and_revokes_token(
        self, client, session
    ) -> None:
        """
        Login → Logout → tentar usar o mesmo access_token novamente.
        O token revogado deve retornar 401 (JTI na blacklist do Redis).
        """
        await UserFactory.create(
            session,
            email="logout_revoke@e2e.com",
            password_hash=hash_password(_PLAIN_PASSWORD),
        )
        tokens = await _login_mobile(client, "logout_revoke@e2e.com", _PLAIN_PASSWORD)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        # Logout: deve retornar 200 e mensagem de confirmação
        response = await client.post("/auth/logout", headers=headers)
        assert response.status_code == 200
        assert "Logout realizado" in response.json()["message"]

        # Usar o mesmo token após logout deve retornar 401 (blacklisted)
        response_revoked = await client.post("/auth/logout", headers=headers)
        assert response_revoked.status_code == 401

    async def test_logout_web_clears_cookie(self, client, session) -> None:
        """
        Cliente web: o logout deve limpar o Cookie HttpOnly do refresh_token
        (Set-Cookie na resposta com o cookie expirado).
        """
        await UserFactory.create(
            session,
            email="logout_web@e2e.com",
            password_hash=hash_password(_PLAIN_PASSWORD),
        )
        # Login web: access_token no body + refresh_token no cookie
        login_response = await client.post(
            "/auth/login",
            json={
                "email": "logout_web@e2e.com",
                "password": _PLAIN_PASSWORD,
                "client_type": "web",
            },
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # Logout: o AsyncClient envia o cookie automaticamente; a resposta deve limpá-lo
        response = await client.post("/auth/logout", headers=headers)

        assert response.status_code == 200
        # Verifica que a resposta contém um Set-Cookie referenciando o refresh_token
        assert "refresh_token" in response.headers.get("set-cookie", "")

    async def test_logout_returns_401_without_auth(self, client, session) -> None:
        """Sem header Authorization → 401 Unauthorized."""
        response = await client.post("/auth/logout")

        assert response.status_code == 401
