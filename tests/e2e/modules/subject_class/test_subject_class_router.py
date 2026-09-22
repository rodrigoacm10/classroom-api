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
        items = list_res.json()["items"]
        assert len(items) >= 1
        listed = next(item for item in items if item["id"] == sc_id)
        assert listed["name"] == "Turma 101"
        assert listed["professor_name"] == user.name
        assert listed["student_count"] == 0
        assert listed["attendance_rate"] == 0.0

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
        ids = [item["id"] for item in list_res.json()["items"]]
        assert sc_id not in ids

        patch_res = await client.patch(f"/tenants/{tenant.id}/subject-classes/{sc_id}", json={"name": "Novo"}, headers=headers)
        assert patch_res.status_code == 404

        del_again_res = await client.delete(f"/tenants/{tenant.id}/subject-classes/{sc_id}", headers=headers)
        assert del_again_res.status_code == 404

    async def test_list_subject_classes_includes_professor_students_and_attendance(self, client, session):
        """GET /subject-classes deve devolver nome do professor, alunos ativos e taxa de presença."""
        admin_user = await UserFactory.create(session, name="Admin List")
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin_user.id, role=UserRole.ADMIN
        )
        admin_headers = {
            "Authorization": f"Bearer {create_access_token(user_id=admin_user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)}"
        }

        prof_user = await UserFactory.create(session, name="Prof Carlos")
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof_user.id, role=UserRole.PROFESSOR
        )
        prof_headers = {
            "Authorization": f"Bearer {create_access_token(user_id=prof_user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value)}"
        }

        room_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Lab Lista", "latitude": -8.0476, "longitude": -34.8770},
            headers=admin_headers,
        )
        assert room_res.status_code == 201
        room_id = room_res.json()["id"]

        sc_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_id, "name": "Turma Lista", "discipline_name": "POO"},
            headers=prof_headers,
        )
        assert sc_res.status_code == 201
        sc_id = sc_res.json()["id"]

        students = []
        for i in range(2):
            student_user = await UserFactory.create(session, name=f"Aluno Lista {i + 1}")
            student_member = await TenantFactory.create_member(
                session, tenant_id=tenant.id, user_id=student_user.id, role=UserRole.ALUNO
            )
            enroll_res = await client.post(
                f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
                json={"tenant_member_id": str(student_member.id)},
                headers=admin_headers,
            )
            assert enroll_res.status_code == 201
            students.append(
                {
                    "headers": {
                        "Authorization": f"Bearer {create_access_token(user_id=student_user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value)}",
                        "User-Agent": "okhttp/4.9.0",
                    }
                }
            )

        open_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions",
            json={"room_id": room_id, "duration_minutes": 20},
            headers=prof_headers,
        )
        assert open_res.status_code == 201
        session_data = open_res.json()

        confirm_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_data['id']}/confirm",
            json={
                "day_code": session_data["day_code"],
                "latitude": -8.04761,
                "longitude": -34.87701,
            },
            headers=students[0]["headers"],
        )
        assert confirm_res.status_code == 201

        list_res = await client.get(f"/tenants/{tenant.id}/subject-classes", headers=prof_headers)
        assert list_res.status_code == 200
        listed = next(item for item in list_res.json()["items"] if item["id"] == sc_id)
        assert listed["name"] == "Turma Lista"
        assert listed["discipline_name"] == "POO"
        assert listed["professor_name"] == "Prof Carlos"
        assert listed["student_count"] == 2
        assert listed["attendance_rate"] == 0.5

    async def test_list_subject_classes_filters_by_professor_id(self, client, session):
        """GET /subject-classes?professor_id= filtra turmas pelo professor responsável."""
        admin_user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin_user.id, role=UserRole.ADMIN
        )
        admin_headers = {
            "Authorization": f"Bearer {create_access_token(user_id=admin_user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)}"
        }

        prof_a = await UserFactory.create(session, name="Prof A")
        member_a = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof_a.id, role=UserRole.PROFESSOR
        )
        prof_a_headers = {
            "Authorization": f"Bearer {create_access_token(user_id=prof_a.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value)}"
        }

        prof_b = await UserFactory.create(session, name="Prof B")
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof_b.id, role=UserRole.PROFESSOR
        )
        prof_b_headers = {
            "Authorization": f"Bearer {create_access_token(user_id=prof_b.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value)}"
        }

        room_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Lab Filtro", "latitude": -8.0, "longitude": -34.0},
            headers=admin_headers,
        )
        room_id = room_res.json()["id"]

        class_a = await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_id, "name": "Turma do A", "discipline_name": "POO"},
            headers=prof_a_headers,
        )
        class_b = await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_id, "name": "Turma do B", "discipline_name": "Cálculo"},
            headers=prof_b_headers,
        )
        assert class_a.status_code == 201
        assert class_b.status_code == 201
        class_a_id = class_a.json()["id"]

        filtered = await client.get(
            f"/tenants/{tenant.id}/subject-classes",
            params={"professor_id": str(member_a.id)},
            headers=admin_headers,
        )
        assert filtered.status_code == 200
        items = filtered.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == class_a_id
        assert items[0]["professor_id"] == str(member_a.id)
        assert items[0]["professor_name"] == "Prof A"
        assert items[0]["name"] == "Turma do A"

    async def test_list_subject_classes_filters_by_room_id(self, client, session):
        """GET /subject-classes?room_id= filtra turmas pela sala vinculada."""
        admin_user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin_user.id, role=UserRole.ADMIN
        )
        headers = {
            "Authorization": f"Bearer {create_access_token(user_id=admin_user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)}"
        }

        room_a_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Sala A", "latitude": -8.0, "longitude": -34.0},
            headers=headers,
        )
        room_b_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Sala B", "latitude": -8.1, "longitude": -34.1},
            headers=headers,
        )
        assert room_a_res.status_code == 201
        assert room_b_res.status_code == 201
        room_a_id = room_a_res.json()["id"]
        room_b_id = room_b_res.json()["id"]

        class_a = await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_a_id, "name": "Turma Sala A", "discipline_name": "POO"},
            headers=headers,
        )
        class_b = await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_b_id, "name": "Turma Sala B", "discipline_name": "Cálculo"},
            headers=headers,
        )
        assert class_a.status_code == 201
        assert class_b.status_code == 201
        class_a_id = class_a.json()["id"]

        unfiltered = await client.get(f"/tenants/{tenant.id}/subject-classes", headers=headers)
        assert unfiltered.status_code == 200
        assert len(unfiltered.json()["items"]) == 2

        filtered = await client.get(
            f"/tenants/{tenant.id}/subject-classes",
            params={"room_id": room_a_id},
            headers=headers,
        )
        assert filtered.status_code == 200
        items = filtered.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == class_a_id
        assert items[0]["room_id"] == room_a_id
        assert items[0]["name"] == "Turma Sala A"
        assert items[0]["discipline_name"] == "POO"
        assert items[0]["professor_name"] == admin_user.name
        assert items[0]["student_count"] == 0
        assert items[0]["attendance_rate"] == 0.0

    async def test_list_subject_classes_pagination_and_search(self, client, session):
        """GET /subject-classes -> Deve suportar paginação offset e busca por nome/disciplina."""
        admin_user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin_user.id, role=UserRole.ADMIN
        )
        headers = {
            "Authorization": f"Bearer {create_access_token(user_id=admin_user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)}"
        }

        room_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Sala Pag", "latitude": -8.0, "longitude": -34.0},
            headers=headers,
        )
        room_id = room_res.json()["id"]

        await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_id, "name": "Turma 101", "discipline_name": "Matemática 1"},
            headers=headers,
        )
        await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_id, "name": "Turma 102", "discipline_name": "Matemática 2"},
            headers=headers,
        )
        await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_id, "name": "Turma 201", "discipline_name": "História 1"},
            headers=headers,
        )

        # Test pagination
        res_p1 = await client.get(
            f"/tenants/{tenant.id}/subject-classes?page=1&page_size=2",
            headers=headers,
        )
        assert res_p1.status_code == 200
        p1_data = res_p1.json()
        assert len(p1_data["items"]) == 2
        assert p1_data["total"] == 3
        assert p1_data["page"] == 1
        assert p1_data["page_size"] == 2
        assert p1_data["pages"] == 2

        # Test search
        res_search = await client.get(
            f"/tenants/{tenant.id}/subject-classes?search=Matemática",
            headers=headers,
        )
        assert res_search.status_code == 200
        search_data = res_search.json()
        assert len(search_data["items"]) == 2
        assert search_data["total"] == 2
