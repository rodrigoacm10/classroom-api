from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from infra.database.models.tenant_invite import TenantInviteModel
from security.jwt import create_access_token
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestInviteRouterEndpoints:
    """Testes E2E para as rotas do sistema de convites (Invites)."""

    @patch("modules.tenant.application.use_cases.send_invite.send_invite_email")
    async def test_send_invite_success(self, mock_send_email, client, session):
        """POST /tenants/{id}/invites -> Deve enviar convite e disparar e-mail com sucesso quando for ADMIN."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "email": "novo_prof@escola.com",
            "role": "professor",
        }

        response = await client.post(f"/tenants/{tenant.id}/invites", json=payload, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "novo_prof@escola.com"
        assert data["role"] == "professor"
        assert data["status"] == "pending"
        assert data["tenant_id"] == str(tenant.id)
        assert mock_send_email.called

    async def test_send_invite_requires_admin_role(self, client, session):
        """POST /tenants/{id}/invites -> Deve retornar 403 Forbidden se o usuário não for ADMIN."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value)
        headers = {"Authorization": f"Bearer {token}"}

        payload = {"email": "aluno@escola.com", "role": "aluno"}
        response = await client.post(f"/tenants/{tenant.id}/invites", json=payload, headers=headers)
        assert response.status_code == 403

    async def test_get_invite_details_public_success(self, client, session):
        """GET /invites/{token} -> Deve retornar os detalhes públicos do convite sem exigir autenticação."""
        tenant = await TenantFactory.create(session, name="Escola Publica")
        invite_model = TenantInviteModel(
            tenant_id=tenant.id,
            email="aluno_novo@escola.com",
            role=UserRole.ALUNO,
            token="token-teste-123",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
        )
        session.add(invite_model)
        await session.flush()

        response = await client.get(f"/invites/{invite_model.token}")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "aluno_novo@escola.com"
        assert data["tenant_name"] == "Escola Publica"
        assert data["status"] == "pending"

    async def test_get_invite_details_not_found(self, client):
        """GET /invites/{token} -> Deve retornar 404 Not Found se o token não existir."""
        response = await client.get("/invites/token-inexistente-999")
        assert response.status_code == 404

    async def test_accept_invite_success(self, client, session):
        """POST /invites/{token}/accept -> Deve aceitar o convite e vincular o usuário logado à tenant."""
        tenant = await TenantFactory.create(session)
        invited_user = await UserFactory.create(session, email="aluno_aceita@escola.com")

        invite_model = TenantInviteModel(
            tenant_id=tenant.id,
            email="aluno_aceita@escola.com",
            role=UserRole.ALUNO,
            token="token-aceite-valido",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
        )
        session.add(invite_model)
        await session.flush()

        token = create_access_token(user_id=invited_user.id)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(f"/invites/{invite_model.token}/accept", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == str(tenant.id)
        assert data["user_id"] == str(invited_user.id)
        assert data["role"] == "aluno"

    async def test_accept_invite_different_user_email_forbidden(self, client, session):
        """POST /invites/{token}/accept -> Deve retornar 403 Forbidden se o e-mail do usuário não coincidir."""
        tenant = await TenantFactory.create(session)
        wrong_user = await UserFactory.create(session, email="outro_usuario@escola.com")

        invite_model = TenantInviteModel(
            tenant_id=tenant.id,
            email="dono_do_convite@escola.com",
            role=UserRole.PROFESSOR,
            token="token-dono-especifico",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
        )
        session.add(invite_model)
        await session.flush()

        token = create_access_token(user_id=wrong_user.id)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(f"/invites/{invite_model.token}/accept", headers=headers)
        assert response.status_code == 403
        assert "outro endereço de e-mail" in response.json()["detail"]

    async def test_accept_invite_expired_bad_request(self, client, session):
        """POST /invites/{token}/accept -> Deve retornar 400 Bad Request se o convite estiver expirado."""
        tenant = await TenantFactory.create(session)
        invited_user = await UserFactory.create(session, email="usuario_expirado@escola.com")

        invite_model = TenantInviteModel(
            tenant_id=tenant.id,
            email="usuario_expirado@escola.com",
            role=UserRole.ALUNO,
            token="token-expirado-123",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        session.add(invite_model)
        await session.flush()

        token = create_access_token(user_id=invited_user.id)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(f"/invites/{invite_model.token}/accept", headers=headers)
        assert response.status_code == 400
        assert "expirado" in response.json()["detail"]

    async def test_accept_invite_already_accepted_bad_request(self, client, session):
        """POST /invites/{token}/accept -> Deve retornar 400 Bad Request se o convite já tiver sido aceito."""
        tenant = await TenantFactory.create(session)
        invited_user = await UserFactory.create(session, email="usuario_ja_aceitou@escola.com")

        invite_model = TenantInviteModel(
            tenant_id=tenant.id,
            email="usuario_ja_aceitou@escola.com",
            role=UserRole.PROFESSOR,
            token="token-ja-aceito-123",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            accepted_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        session.add(invite_model)
        await session.flush()

        token = create_access_token(user_id=invited_user.id)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(f"/invites/{invite_model.token}/accept", headers=headers)
        assert response.status_code == 400
        assert "já foi aceito" in response.json()["detail"]
