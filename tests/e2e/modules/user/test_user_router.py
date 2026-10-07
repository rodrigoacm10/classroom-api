import uuid

import pytest

from security.jwt import create_access_token
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestUserRouterEndpoints:
    """Testes E2E para as rotas do módulo User (/users)."""

    # ─── GET /users/me ────────────────────────────────────────────────────────

    async def test_get_my_profile_success_without_tenant(self, client, session) -> None:
        """GET /users/me -> Retorna 200 com os dados do perfil e tenant_id/role nulos com token base."""
        user = await UserFactory.create(
            session,
            name="Professora Ana",
            email="ana.prof@escola.edu.br",
        )
        token = create_access_token(user_id=user.id)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.get("/users/me", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(user.id)
        assert data["name"] == "Professora Ana"
        assert data["email"] == "ana.prof@escola.edu.br"
        assert data["tenant_id"] is None
        assert data["role"] is None
        assert "created_at" in data

    async def test_get_my_profile_with_tenant_and_role(self, client, session) -> None:
        """GET /users/me -> Retorna 200 com tenant_id e role quando o token está escopado."""
        user = await UserFactory.create(
            session,
            name="Professora Ana",
            email="ana.professor@escola.edu.br",
        )
        fake_tenant_id = uuid.uuid4()
        token = create_access_token(
            user_id=user.id,
            tenant_id=fake_tenant_id,
            role="professor",
        )
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.get("/users/me", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(user.id)
        assert data["name"] == "Professora Ana"
        assert data["email"] == "ana.professor@escola.edu.br"
        assert data["tenant_id"] == str(fake_tenant_id)
        assert data["role"] == "professor"

    async def test_get_my_profile_unauthorized_without_token(self, client) -> None:
        """GET /users/me -> Retorna 401 ou 403 quando não há token de autorização."""
        response = await client.get("/users/me")
        assert response.status_code in (401, 403)

    async def test_get_my_profile_unauthorized_with_invalid_token(self, client) -> None:
        """GET /users/me -> Retorna 401 quando o token é inválido."""
        headers = {"Authorization": "Bearer invalid_or_malformed_token"}
        response = await client.get("/users/me", headers=headers)
        assert response.status_code == 401

    async def test_get_my_profile_unauthorized_when_user_deleted_or_not_found(self, client) -> None:
        """GET /users/me -> Retorna 401 quando o user_id do token não existe no banco."""
        non_existent_id = uuid.uuid4()
        token = create_access_token(user_id=non_existent_id)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.get("/users/me", headers=headers)
        assert response.status_code == 401
        assert response.json()["detail"] == "Usuário não encontrado."

    async def test_get_my_profile_unauthorized_after_logout(self, client, session) -> None:
        """GET /users/me -> Retorna 401 quando o token foi revogado no logout."""
        user = await UserFactory.create(session)
        token = create_access_token(user_id=user.id)
        headers = {"Authorization": f"Bearer {token}"}

        # Faz logout revogando o JTI no Redis
        logout_res = await client.post("/auth/logout", headers=headers)
        assert logout_res.status_code == 200

        # Tentar acessar /users/me com o mesmo token agora deve falhar
        response = await client.get("/users/me", headers=headers)
        assert response.status_code == 401
        assert "revogado" in response.json()["detail"].lower()

    # ─── POST /users/ ─────────────────────────────────────────────────────────

    async def test_create_user_success(self, client) -> None:
        """POST /users/ -> Cria um novo usuário com sucesso (201 Created)."""
        unique_email = f"user_{uuid.uuid4().hex[:8]}@escola.edu.br"
        payload = {
            "name": "Carlos Souza",
            "email": unique_email,
            "password": "Password123!",
        }

        response = await client.post("/users/", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Carlos Souza"
        assert data["email"] == unique_email
        assert "id" in data
        assert "created_at" in data

    async def test_create_user_duplicate_email(self, client, session) -> None:
        """POST /users/ -> Retorna 409 Conflict se o e-mail já estiver cadastrado."""
        existing_user = await UserFactory.create(session, email="existente@escola.edu.br")

        payload = {
            "name": "Outro Nome",
            "email": existing_user.email,
            "password": "Password123!",
        }

        response = await client.post("/users/", json=payload)
        assert response.status_code == 409
        assert "já cadastrado" in response.json()["detail"].lower()
