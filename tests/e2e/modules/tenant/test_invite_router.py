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

    async def test_revoke_invite_success(self, client, session):
        """DELETE /tenants/{id}/invites/{invite_id} -> Deve revogar convite pendente com sucesso quando for ADMIN."""
        admin = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=admin.id, role=UserRole.ADMIN)

        invite_model = TenantInviteModel(
            tenant_id=tenant.id,
            email="para_revogar@escola.com",
            role=UserRole.PROFESSOR,
            token="token-para-revogar-123",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        session.add(invite_model)
        await session.flush()

        token = create_access_token(user_id=admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.delete(f"/tenants/{tenant.id}/invites/{invite_model.id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "revoked"
        assert data["id"] == str(invite_model.id)

    async def test_accept_revoked_invite_bad_request(self, client, session):
        """POST /invites/{token}/accept -> Deve retornar 400 Bad Request ao tentar aceitar convite revogado."""
        tenant = await TenantFactory.create(session)
        invited_user = await UserFactory.create(session, email="usuario_revogado@escola.com")

        invite_model = TenantInviteModel(
            tenant_id=tenant.id,
            email="usuario_revogado@escola.com",
            role=UserRole.ALUNO,
            token="token-revogado-456",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            revoked_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        session.add(invite_model)
        await session.flush()

        token = create_access_token(user_id=invited_user.id)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(f"/invites/{invite_model.token}/accept", headers=headers)
        assert response.status_code == 400
        assert "revogado" in response.json()["detail"]

    # ─── GET /tenants/{tenant_id}/invites (Paginated) ──────────────────────

    async def test_list_tenant_invites_admin_success(self, client, session):
        """GET /tenants/{tenant_id}/invites -> Deve listar convites paginados com sucesso quando for ADMIN."""
        admin = await UserFactory.create(session)
        tenant = await TenantFactory.create(session, name="Escola Listagem E2E")
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=admin.id, role=UserRole.ADMIN)

        inv1 = TenantInviteModel(
            tenant_id=tenant.id,
            email="convite1@escola.com",
            role=UserRole.ALUNO,
            token="token-list-1",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        inv2 = TenantInviteModel(
            tenant_id=tenant.id,
            email="convite2@escola.com",
            role=UserRole.PROFESSOR,
            token="token-list-2",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        inv3 = TenantInviteModel(
            tenant_id=tenant.id,
            email="convite3@escola.com",
            role=UserRole.COORDENADOR,
            token="token-list-3",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        session.add_all([inv1, inv2, inv3])
        await session.flush()

        token = create_access_token(user_id=admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.get(f"/tenants/{tenant.id}/invites?page=1&page_size=2", headers=headers)
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["pages"] == 2
        assert len(data["items"]) == 2

        first_item = data["items"][0]
        assert "id" in first_item
        assert first_item["tenant_id"] == str(tenant.id)
        assert first_item["tenant_name"] == "Escola Listagem E2E"
        assert first_item["status"] == "pending"

    async def test_list_tenant_invites_requires_admin_role(self, client, session):
        """GET /tenants/{tenant_id}/invites -> Deve retornar 403 Forbidden para não-ADMIN."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.get(f"/tenants/{tenant.id}/invites", headers=headers)
        assert response.status_code == 403

    async def test_list_tenant_invites_filter_by_status(self, client, session):
        """GET /tenants/{tenant_id}/invites -> Deve filtrar por status (ex.: pending vs accepted)."""
        admin = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=admin.id, role=UserRole.ADMIN)

        inv_pending = TenantInviteModel(
            tenant_id=tenant.id,
            email="pend@escola.com",
            role=UserRole.ALUNO,
            token="token-pend-filter",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        inv_accepted = TenantInviteModel(
            tenant_id=tenant.id,
            email="acc@escola.com",
            role=UserRole.ALUNO,
            token="token-acc-filter",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            accepted_at=datetime.now(timezone.utc),
        )
        session.add_all([inv_pending, inv_accepted])
        await session.flush()

        token = create_access_token(user_id=admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        resp_pending = await client.get(f"/tenants/{tenant.id}/invites?status=pending", headers=headers)
        assert resp_pending.status_code == 200
        data_p = resp_pending.json()
        assert data_p["total"] == 1
        assert data_p["items"][0]["email"] == "pend@escola.com"
        assert data_p["items"][0]["status"] == "pending"

        resp_accepted = await client.get(f"/tenants/{tenant.id}/invites?status=accepted", headers=headers)
        assert resp_accepted.status_code == 200
        data_a = resp_accepted.json()
        assert data_a["total"] == 1
        assert data_a["items"][0]["email"] == "acc@escola.com"
        assert data_a["items"][0]["status"] == "accepted"

    async def test_list_tenant_invites_tenant_not_found(self, client, session):
        """GET /tenants/{tenant_id}/invites -> Deve retornar 404 Not Found se a tenant não existir."""
        from uuid import uuid4

        admin = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=admin.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        non_existent_tenant_id = uuid4()
        response = await client.get(f"/tenants/{non_existent_tenant_id}/invites", headers=headers)
        assert response.status_code == 404
