import uuid

import pytest

from security.jwt import create_access_token
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestRoomRouterEndpoints:
    """Testes E2E para as rotas do módulo Room (/tenants/{tenant_id}/rooms)."""

    async def test_create_room_success(self, client, session):
        """POST /tenants/{id}/rooms -> ADMIN deve conseguir criar uma sala com geolocalização."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "name": "Auditório Magna",
            "latitude": -8.0476,
            "longitude": -34.8770,
            "tolerance_radius_meters": 60,
        }

        response = await client.post(f"/tenants/{tenant.id}/rooms", json=payload, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Auditório Magna"
        assert data["latitude"] == -8.0476
        assert data["longitude"] == -34.8770
        assert data["tolerance_radius_meters"] == 60
        assert data["tenant_id"] == str(tenant.id)
        assert data["created_by"] == str(user.id)

    async def test_create_room_forbidden_for_student(self, client, session):
        """POST /tenants/{id}/rooms -> Papel ALUNO deve receber 403 Forbidden."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value)
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "name": "Sala do Aluno",
            "latitude": -8.0476,
            "longitude": -34.8770,
            "tolerance_radius_meters": 50,
        }

        response = await client.post(f"/tenants/{tenant.id}/rooms", json=payload, headers=headers)
        assert response.status_code == 403

    async def test_create_room_invalid_latitude_validation(self, client, session):
        """POST /tenants/{id}/rooms -> Latitude > 90 deve retornar 422 Unprocessable Entity."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "name": "Sala Inválida",
            "latitude": 95.0,  # Inválido
            "longitude": -34.8770,
        }

        response = await client.post(f"/tenants/{tenant.id}/rooms", json=payload, headers=headers)
        assert response.status_code == 422

    async def test_list_rooms_success(self, client, session):
        """GET /tenants/{id}/rooms -> Deve listar salas da tenant."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value)
        headers = {"Authorization": f"Bearer {token}"}

        # Criar duas salas via API
        payload1 = {"name": "Lab 1", "latitude": -8.0, "longitude": -34.0, "tolerance_radius_meters": 30}
        payload2 = {"name": "Lab 2", "latitude": -8.1, "longitude": -34.1, "tolerance_radius_meters": 40}

        await client.post(f"/tenants/{tenant.id}/rooms", json=payload1, headers=headers)
        await client.post(f"/tenants/{tenant.id}/rooms", json=payload2, headers=headers)

        response = await client.get(f"/tenants/{tenant.id}/rooms", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = [r["name"] for r in data]
        assert "Lab 1" in names
        assert "Lab 2" in names

    async def test_get_room_by_id_success(self, client, session):
        """GET /tenants/{id}/rooms/{room_id} -> Deve retornar a sala por ID."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        create_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Sala Específica", "latitude": -8.0, "longitude": -34.0},
            headers=headers,
        )
        room_id = create_res.json()["id"]

        response = await client.get(f"/tenants/{tenant.id}/rooms/{room_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["name"] == "Sala Específica"

    async def test_patch_room_success(self, client, session):
        """PATCH /tenants/{id}/rooms/{room_id} -> Atualização parcial de atributos."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value)
        headers = {"Authorization": f"Bearer {token}"}

        create_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Nome Antigo", "latitude": -8.0, "longitude": -34.0, "tolerance_radius_meters": 50},
            headers=headers,
        )
        room_id = create_res.json()["id"]

        patch_payload = {"name": "Nome Atualizado", "tolerance_radius_meters": 100}
        patch_res = await client.patch(f"/tenants/{tenant.id}/rooms/{room_id}", json=patch_payload, headers=headers)
        assert patch_res.status_code == 200
        data = patch_res.json()
        assert data["name"] == "Nome Atualizado"
        assert data["tolerance_radius_meters"] == 100
        assert data["latitude"] == -8.0

    async def test_delete_room_success(self, client, session):
        """DELETE /tenants/{id}/rooms/{room_id} -> ADMIN remove sala e retorna 204."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        create_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Sala Para Deletar", "latitude": -8.0, "longitude": -34.0},
            headers=headers,
        )
        room_id = create_res.json()["id"]

        delete_res = await client.delete(f"/tenants/{tenant.id}/rooms/{room_id}", headers=headers)
        assert delete_res.status_code == 204

        get_res = await client.get(f"/tenants/{tenant.id}/rooms/{room_id}", headers=headers)
        assert get_res.status_code == 404

    async def test_delete_room_forbidden_for_professor(self, client, session):
        """DELETE /tenants/{id}/rooms/{room_id} -> PROFESSOR não tem permissão para deletar salas (somente ADMIN) -> 403."""
        user_admin = await UserFactory.create(session)
        user_prof = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user_admin.id, role=UserRole.ADMIN)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user_prof.id, role=UserRole.PROFESSOR)

        admin_token = create_access_token(user_id=user_admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        prof_token = create_access_token(user_id=user_prof.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value)

        # Admin cria a sala
        create_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Sala Protegida", "latitude": -8.0, "longitude": -34.0},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        room_id = create_res.json()["id"]

        # Professor tenta deletar
        delete_res = await client.delete(
            f"/tenants/{tenant.id}/rooms/{room_id}",
            headers={"Authorization": f"Bearer {prof_token}"},
        )
        assert delete_res.status_code == 403

    async def test_cannot_get_patch_or_delete_already_soft_deleted_room(self, client, session):
        """Salas deletadas logicamente (soft delete) devem retornar 404 em GET, PATCH e novas chamadas de DELETE."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Cria a sala
        create_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Sala Soft Delete Test", "latitude": -8.0, "longitude": -34.0},
            headers=headers,
        )
        room_id = create_res.json()["id"]

        # 2. Deleta a sala (Soft Delete -> status 204)
        del_res = await client.delete(f"/tenants/{tenant.id}/rooms/{room_id}", headers=headers)
        assert del_res.status_code == 204

        # 3. GET por ID deve retornar 404
        get_res = await client.get(f"/tenants/{tenant.id}/rooms/{room_id}", headers=headers)
        assert get_res.status_code == 404

        # 4. GET listagem não deve incluir a sala
        list_res = await client.get(f"/tenants/{tenant.id}/rooms", headers=headers)
        assert list_res.status_code == 200
        room_ids = [r["id"] for r in list_res.json()]
        assert room_id not in room_ids

        # 5. PATCH deve retornar 404
        patch_res = await client.patch(
            f"/tenants/{tenant.id}/rooms/{room_id}",
            json={"name": "Tentativa de Edicao"},
            headers=headers,
        )
        assert patch_res.status_code == 404

        # 6. Novo DELETE deve retornar 404
        second_del_res = await client.delete(f"/tenants/{tenant.id}/rooms/{room_id}", headers=headers)
        assert second_del_res.status_code == 404

    async def test_create_room_success_for_professor(self, client, session):
        """POST /tenants/{id}/rooms -> PROFESSOR também deve conseguir criar salas (201)."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value)
        headers = {"Authorization": f"Bearer {token}"}

        payload = {"name": "Sala do Professor", "latitude": -8.0, "longitude": -34.0}
        response = await client.post(f"/tenants/{tenant.id}/rooms", json=payload, headers=headers)
        assert response.status_code == 201
        assert response.json()["name"] == "Sala do Professor"

    async def test_patch_room_forbidden_for_student(self, client, session):
        """PATCH /tenants/{id}/rooms/{room_id} -> Papel ALUNO deve receber 403 Forbidden ao tentar editar."""
        user_admin = await UserFactory.create(session)
        user_student = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user_admin.id, role=UserRole.ADMIN)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user_student.id, role=UserRole.ALUNO)

        admin_token = create_access_token(user_id=user_admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        student_token = create_access_token(user_id=user_student.id, tenant_id=tenant.id, role=UserRole.ALUNO.value)

        create_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Sala Original", "latitude": -8.0, "longitude": -34.0},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        room_id = create_res.json()["id"]

        patch_res = await client.patch(
            f"/tenants/{tenant.id}/rooms/{room_id}",
            json={"name": "Alvo de Aluno"},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert patch_res.status_code == 403

    async def test_list_and_get_room_allowed_for_student(self, client, session):
        """GET /tenants/{id}/rooms -> Papel ALUNO deve conseguir listar e visualizar salas (200)."""
        user_admin = await UserFactory.create(session)
        user_student = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user_admin.id, role=UserRole.ADMIN)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user_student.id, role=UserRole.ALUNO)

        admin_token = create_access_token(user_id=user_admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        student_token = create_access_token(user_id=user_student.id, tenant_id=tenant.id, role=UserRole.ALUNO.value)

        create_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Sala Visível ao Aluno", "latitude": -8.0, "longitude": -34.0},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        room_id = create_res.json()["id"]

        # Listagem por Aluno -> 200
        list_res = await client.get(f"/tenants/{tenant.id}/rooms", headers={"Authorization": f"Bearer {student_token}"})
        assert list_res.status_code == 200
        assert len(list_res.json()) >= 1

        # Busca por ID por Aluno -> 200
        get_res = await client.get(f"/tenants/{tenant.id}/rooms/{room_id}", headers={"Authorization": f"Bearer {student_token}"})
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "Sala Visível ao Aluno"


