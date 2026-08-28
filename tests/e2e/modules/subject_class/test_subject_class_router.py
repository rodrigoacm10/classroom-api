import pytest

from security.jwt import create_access_token
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestSubjectClassRouterEndpoints:
    """Testes E2E para as rotas do módulo SubjectClass (/tenants/{tenant_id}/subject-classes)."""

    async def test_create_subject_class_success_admin(self, client, session):
        """POST /tenants/{id}/subject-classes -> ADMIN deve conseguir criar uma turma com sucesso."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        room_payload = {"name": "Auditório 1", "latitude": -8.0476, "longitude": -34.8770}
        room_res = await client.post(f"/tenants/{tenant.id}/rooms", json=room_payload, headers=headers)
        assert room_res.status_code == 201
        room_id = room_res.json()["id"]

        sc_payload = {
            "room_id": room_id,
            "name": "Turma A - Noturno",
            "discipline_name": "Engenharia de Software",
        }

        response = await client.post(f"/tenants/{tenant.id}/subject-classes", json=sc_payload, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Turma A - Noturno"
        assert data["discipline_name"] == "Engenharia de Software"
        assert data["room_id"] == room_id
        assert data["tenant_id"] == str(tenant.id)
        assert data["professor_id"] == str(member.id)

    async def test_create_subject_class_success_professor(self, client, session):
        """POST /tenants/{id}/subject-classes -> PROFESSOR deve conseguir criar uma turma com sucesso."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value)
        headers = {"Authorization": f"Bearer {token}"}

        room_payload = {"name": "Lab 3", "latitude": -8.0, "longitude": -34.0}
        room_res = await client.post(f"/tenants/{tenant.id}/rooms", json=room_payload, headers=headers)
        room_id = room_res.json()["id"]

        sc_payload = {
            "room_id": room_id,
            "name": "Turma B - Vespertino",
            "discipline_name": "Sistemas Operacionais",
        }

        response = await client.post(f"/tenants/{tenant.id}/subject-classes", json=sc_payload, headers=headers)
        assert response.status_code == 201
        assert response.json()["name"] == "Turma B - Vespertino"

    async def test_create_subject_class_forbidden_for_student(self, client, session):
        """POST /tenants/{id}/subject-classes -> Papel ALUNO deve receber 403 Forbidden."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value)
        headers = {"Authorization": f"Bearer {token}"}

        sc_payload = {
            "room_id": "00000000-0000-0000-0000-000000000000",
            "name": "Turma Aluno",
            "discipline_name": "Matemática",
        }

        response = await client.post(f"/tenants/{tenant.id}/subject-classes", json=sc_payload, headers=headers)
        assert response.status_code == 403

    async def test_create_subject_class_with_soft_deleted_room_fails(self, client, session):
        """POST /tenants/{id}/subject-classes -> Criar turma apontando para sala com soft delete deve retornar 404 Not Found."""
        admin_user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=admin_user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=admin_user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        room_res = await client.post(f"/tenants/{tenant.id}/rooms", json={"name": "Sala Para Deletar", "latitude": -8.0, "longitude": -34.0}, headers=headers)
        room_id = room_res.json()["id"]

        await client.delete(f"/tenants/{tenant.id}/rooms/{room_id}", headers=headers)

        sc_payload = {
            "room_id": room_id,
            "name": "Turma Sala Deletada",
            "discipline_name": "Física",
        }
        response = await client.post(f"/tenants/{tenant.id}/subject-classes", json=sc_payload, headers=headers)
        assert response.status_code == 404

    async def test_list_and_get_subject_classes(self, client, session):
        """GET /tenants/{id}/subject-classes e GET /tenants/{id}/subject-classes/{id} -> Deve listar turmas e obter turma por ID."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        room_res = await client.post(f"/tenants/{tenant.id}/rooms", json={"name": "Lab 1", "latitude": -8.0, "longitude": -34.0}, headers=headers)
        room_id = room_res.json()["id"]

        create_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_id, "name": "Turma 101", "discipline_name": "Cálculo"},
            headers=headers,
        )
        sc_id = create_res.json()["id"]

        list_res = await client.get(f"/tenants/{tenant.id}/subject-classes", headers=headers)
        assert list_res.status_code == 200
        assert len(list_res.json()) >= 1

        get_res = await client.get(f"/tenants/{tenant.id}/subject-classes/{sc_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "Turma 101"

    async def test_patch_subject_class_success(self, client, session):
        """PATCH /tenants/{id}/subject-classes/{id} -> Atualização parcial de dados da turma com sucesso."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR)

        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value)
        headers = {"Authorization": f"Bearer {token}"}

        room_res = await client.post(f"/tenants/{tenant.id}/rooms", json={"name": "Lab 2", "latitude": -8.0, "longitude": -34.0}, headers=headers)
        room_id = room_res.json()["id"]

        create_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_id, "name": "Nome Antigo", "discipline_name": "D1"},
            headers=headers,
        )
        sc_id = create_res.json()["id"]

        patch_res = await client.patch(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}",
            json={"name": "Nome Atualizado"},
            headers=headers,
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["name"] == "Nome Atualizado"
        assert patch_res.json()["discipline_name"] == "D1"

    async def test_delete_subject_class_success_and_subsequent_calls_404(self, client, session):
        """DELETE /tenants/{id}/subject-classes/{id} -> Soft delete com 204 e chamadas subsequentes (GET/PATCH/DELETE) retornando 404."""
        admin_user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=admin_user.id, role=UserRole.ADMIN)

        token = create_access_token(user_id=admin_user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        headers = {"Authorization": f"Bearer {token}"}

        room_res = await client.post(f"/tenants/{tenant.id}/rooms", json={"name": "Lab 5", "latitude": -8.0, "longitude": -34.0}, headers=headers)
        room_id = room_res.json()["id"]

        create_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_id, "name": "Para Deletar", "discipline_name": "D1"},
            headers=headers,
        )
        sc_id = create_res.json()["id"]

        delete_res = await client.delete(f"/tenants/{tenant.id}/subject-classes/{sc_id}", headers=headers)
        assert delete_res.status_code == 204

        get_res = await client.get(f"/tenants/{tenant.id}/subject-classes/{sc_id}", headers=headers)
        assert get_res.status_code == 404

        list_res = await client.get(f"/tenants/{tenant.id}/subject-classes", headers=headers)
        ids = [item["id"] for item in list_res.json()]
        assert sc_id not in ids

        patch_res = await client.patch(f"/tenants/{tenant.id}/subject-classes/{sc_id}", json={"name": "Novo"}, headers=headers)
        assert patch_res.status_code == 404

        del_again_res = await client.delete(f"/tenants/{tenant.id}/subject-classes/{sc_id}", headers=headers)
        assert del_again_res.status_code == 404
