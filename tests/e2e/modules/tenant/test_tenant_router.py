import pytest

from security.jwt import create_access_token
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestTenantRouterEndpoints:
    """Testes E2E para as rotas do módulo Tenant."""

    async def test_create_tenant_success(self, client, session):
        """POST /tenants/ -> Deve criar a tenant e definir o usuário autenticado como ADMIN."""
        user = await UserFactory.create(session)
        token = create_access_token(user_id=user.id)
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "name": "Nova Escola E2E",
            "slug": "nova-escola-e2e",
        }

        response = await client.post("/tenants/", json=payload, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Nova Escola E2E"
        assert data["slug"] == "nova-escola-e2e"
        assert data["active"] is True
        assert data["deleted"] is False

        # Verifica se o criador se tornou automaticamente ADMIN da tenant criada
        me_response = await client.get("/tenants/me", headers=headers)
        assert me_response.status_code == 200
        my_tenants = me_response.json()
        assert len(my_tenants) == 1
        assert my_tenants[0]["id"] == data["id"]
        assert my_tenants[0]["role"] == UserRole.ADMIN.value

    async def test_list_my_tenants_success(self, client, session):
        """GET /tenants/me -> Deve listar as tenants ativas e não deletadas do usuário."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session, name="Minha Escola")
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.get("/tenants/me", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(tenant.id)
        assert data[0]["active"] is True
        assert data[0]["deleted"] is False

    async def test_deactivate_tenant_success(self, client, session):
        """PATCH /tenants/{id}/deactivate -> Deve desativar a tenant quando o usuário for ADMIN."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session, active=True)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.patch(f"/tenants/{tenant.id}/deactivate", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(tenant.id)
        assert data["active"] is False

    async def test_activate_tenant_success(self, client, session):
        """PATCH /tenants/{id}/activate -> Deve ativar a tenant quando o usuário for ADMIN."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session, active=False)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.patch(f"/tenants/{tenant.id}/activate", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(tenant.id)
        assert data["active"] is True

    async def test_soft_delete_tenant_success(self, client, session):
        """DELETE /tenants/{id} -> Deve realizar o soft delete da tenant quando o usuário for ADMIN."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session, active=True, deleted=False)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.delete(f"/tenants/{tenant.id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(tenant.id)
        assert data["deleted"] is True

        # Após o soft delete, GET /tenants/me não deve listar a tenant deletada
        me_response = await client.get("/tenants/me", headers=headers)
        assert me_response.status_code == 200
        assert len(me_response.json()) == 0

    async def test_deactivate_tenant_requires_admin_role(self, client, session):
        """PATCH /tenants/{id}/deactivate -> Deve retornar status 403 se o usuário não for ADMIN."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.patch(f"/tenants/{tenant.id}/deactivate", headers=headers)
        assert response.status_code == 403

    async def test_cannot_switch_to_deactivated_tenant(self, client, session):
        """POST /auth/switch-tenant -> Deve retornar status 403 ao tentar alternar para tenant desativada."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session, active=False, deleted=False)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        base_token = create_access_token(user_id=user.id)
        headers = {"Authorization": f"Bearer {base_token}"}

        response = await client.post("/auth/switch-tenant", json={"tenant_id": str(tenant.id)}, headers=headers)
        assert response.status_code == 403
        assert "desativada" in response.json()["detail"]

    async def test_cannot_switch_to_deleted_tenant(self, client, session):
        """POST /auth/switch-tenant -> Deve retornar status 403 ao tentar alternar para tenant deletada."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session, active=True, deleted=True)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        base_token = create_access_token(user_id=user.id)
        headers = {"Authorization": f"Bearer {base_token}"}

        response = await client.post("/auth/switch-tenant", json={"tenant_id": str(tenant.id)}, headers=headers)
        assert response.status_code == 403
        assert "não encontrada" in response.json()["detail"]

    async def test_remove_tenant_member_success(self, client, session):
        """DELETE /tenants/{id}/members/{user_id} -> Deve realizar o soft delete do membro com sucesso quando for ADMIN."""
        admin = await UserFactory.create(session)
        member_user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)

        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=admin.id, role=UserRole.ADMIN)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=member_user.id, role=UserRole.PROFESSOR)

        token = create_access_token(user_id=admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.delete(f"/tenants/{tenant.id}/members/{member_user.id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(member_user.id)
        assert data["tenant_id"] == str(tenant.id)

    async def test_remove_single_admin_bad_request(self, client, session):
        """DELETE /tenants/{id}/members/{user_id} -> Deve retornar 400 Bad Request ao tentar remover o único ADMIN."""
        admin = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)

        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=admin.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.delete(f"/tenants/{tenant.id}/members/{admin.id}", headers=headers)
        assert response.status_code == 400
        assert "único administrador" in response.json()["detail"]

    async def test_remove_tenant_member_requires_admin_role(self, client, session):
        """DELETE /tenants/{id}/members/{user_id} -> Deve retornar 403 Forbidden se o usuário não for ADMIN."""
        professor = await UserFactory.create(session)
        member_user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)

        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=professor.id, role=UserRole.PROFESSOR)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=member_user.id, role=UserRole.ALUNO)

        # Token do PROFESSOR (não-ADMIN)
        token = create_access_token(user_id=professor.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value)
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.delete(f"/tenants/{tenant.id}/members/{member_user.id}", headers=headers)
        assert response.status_code == 403
        assert "não autorizado" in response.json()["detail"]
