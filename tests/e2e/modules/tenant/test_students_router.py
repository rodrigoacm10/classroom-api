import pytest

from security.jwt import create_access_token
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestStudentsRouter:
    async def test_list_students_success_for_professor_admin_coordenador(self, client, session):
        """GET /members/students e GET /tenants/{id}/students -> Acessível por PROFESSOR, ADMIN e COORDENADOR."""
        admin = await UserFactory.create(session, name="Admin Root", email="admin@test.com")
        coord = await UserFactory.create(session, name="Coordenador Ana", email="ana@test.com")
        prof = await UserFactory.create(session, name="Prof Rodrigo", email="rodrigo@test.com")
        aluno1 = await UserFactory.create(session, name="Lucas Oliveira", email="lucas@aluno.com")
        aluno2 = await UserFactory.create(session, name="Beatriz Santos", email="beatriz@aluno.com")

        tenant = await TenantFactory.create(session)

        # Associa os membros à tenant
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin.id, role=UserRole.ADMIN
        )
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=coord.id, role=UserRole.COORDENADOR
        )
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof.id, role=UserRole.PROFESSOR
        )
        m_aluno1 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=aluno1.id, role=UserRole.ALUNO
        )
        m_aluno2 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=aluno2.id, role=UserRole.ALUNO
        )

        # 1. PROFESSOR acessando /members/students
        prof_token = create_access_token(
            user_id=prof.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value
        )
        res_prof = await client.get(
            "/members/students", headers={"Authorization": f"Bearer {prof_token}"}
        )
        assert res_prof.status_code == 200
        data_prof = res_prof.json()
        assert data_prof["total"] == 2
        assert len(data_prof["items"]) == 2

        # Validação do formato FLAT do aluno
        first_item = data_prof["items"][0]
        assert "id" in first_item
        assert "tenant_member_id" in first_item
        assert "user_id" in first_item
        assert "name" in first_item
        assert "email" in first_item
        assert "role" in first_item
        assert first_item["role"] == "aluno"
        # Sem nesting!
        assert "user" not in first_item

        # 2. COORDENADOR acessando /tenants/{id}/students
        coord_token = create_access_token(
            user_id=coord.id, tenant_id=tenant.id, role=UserRole.COORDENADOR.value
        )
        res_coord = await client.get(
            f"/tenants/{tenant.id}/students", headers={"Authorization": f"Bearer {coord_token}"}
        )
        assert res_coord.status_code == 200
        assert res_coord.json()["total"] == 2

        # 3. ADMIN acessando /tenants/{id}/members/students
        admin_token = create_access_token(
            user_id=admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value
        )
        res_admin = await client.get(
            f"/tenants/{tenant.id}/members/students",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_admin.status_code == 200
        assert res_admin.json()["total"] == 2

    async def test_list_students_forbidden_for_student(self, client, session):
        """GET /members/students -> 403 Forbidden para papel ALUNO."""
        aluno = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=aluno.id, role=UserRole.ALUNO
        )

        token = create_access_token(
            user_id=aluno.id, tenant_id=tenant.id, role=UserRole.ALUNO.value
        )
        res = await client.get("/members/students", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 403

    async def test_list_students_search_filter(self, client, session):
        """GET /members/students?search=beatriz -> Filtra aluno por nome/email."""
        prof = await UserFactory.create(session)
        aluno1 = await UserFactory.create(session, name="Lucas Oliveira", email="lucas@aluno.com")
        aluno2 = await UserFactory.create(session, name="Beatriz Santos", email="beatriz@aluno.com")

        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof.id, role=UserRole.PROFESSOR
        )
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=aluno1.id, role=UserRole.ALUNO
        )
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=aluno2.id, role=UserRole.ALUNO
        )

        token = create_access_token(
            user_id=prof.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value
        )
        headers = {"Authorization": f"Bearer {token}"}

        res = await client.get("/members/students?search=beatriz", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Beatriz Santos"
        assert data["items"][0]["email"] == "beatriz@aluno.com"

    async def test_list_members_returns_flat_name_and_email(self, client, session):
        """GET /tenants/{id}/members -> Agora retorna os campos flat 'name' e 'email' do UserModel."""
        admin = await UserFactory.create(session, name="Admin Chefe", email="admin.chefe@test.com")
        aluno = await UserFactory.create(
            session, name="Mariana Lima", email="mariana.lima@test.com"
        )

        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin.id, role=UserRole.ADMIN
        )
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=aluno.id, role=UserRole.ALUNO
        )

        token = create_access_token(
            user_id=admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value
        )
        res = await client.get(
            f"/tenants/{tenant.id}/members", headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 200
        data = res.json()

        mariana = next(item for item in data["items"] if item["user_id"] == str(aluno.id))
        assert mariana["name"] == "Mariana Lima"
        assert mariana["email"] == "mariana.lima@test.com"
        assert mariana["role"] == "aluno"

    async def test_get_students_metrics_success(self, client, session):
        """GET /members/students/metrics -> Retorna indicadores consolidados de alunos no tenant."""
        admin = await UserFactory.create(session)
        aluno1 = await UserFactory.create(session, name="Aluno 1", email="aluno1@test.com")
        aluno2 = await UserFactory.create(session, name="Aluno 2", email="aluno2@test.com")
        aluno3 = await UserFactory.create(session, name="Aluno 3", email="aluno3@test.com")

        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin.id, role=UserRole.ADMIN
        )
        m_aluno1 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=aluno1.id, role=UserRole.ALUNO
        )
        m_aluno2 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=aluno2.id, role=UserRole.ALUNO
        )
        m_aluno3 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=aluno3.id, role=UserRole.ALUNO
        )

        admin_token = create_access_token(
            user_id=admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value
        )
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Cria uma sala e duas turmas
        room_res = await client.post(
            "/rooms", json={"name": "Sala B", "latitude": -8.0, "longitude": -34.0}, headers=headers
        )
        room_id = room_res.json()["id"]

        sc1_res = await client.post(
            "/subject-classes",
            json={"room_id": room_id, "name": "Turma 1", "discipline_name": "Matemática"},
            headers=headers,
        )
        sc1_id = sc1_res.json()["id"]
        sc2_res = await client.post(
            "/subject-classes",
            json={"room_id": room_id, "name": "Turma 2", "discipline_name": "Física"},
            headers=headers,
        )
        sc2_id = sc2_res.json()["id"]

        # Matricula aluno 1 em 2 turmas, aluno 2 em 1 turma, aluno 3 em 0 turmas
        await client.post(
            f"/subject-classes/{sc1_id}/enrollments",
            json={"tenant_member_id": str(m_aluno1.id)},
            headers=headers,
        )
        await client.post(
            f"/subject-classes/{sc2_id}/enrollments",
            json={"tenant_member_id": str(m_aluno1.id)},
            headers=headers,
        )
        await client.post(
            f"/subject-classes/{sc1_id}/enrollments",
            json={"tenant_member_id": str(m_aluno2.id)},
            headers=headers,
        )

        res = await client.get("/members/students/metrics", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total_students"] == 3
        assert data["total_enrollments"] == 3
        assert data["avg_classes_per_student"] == 1.0  # 3 matrículas / 3 alunos
        assert data["students_no_class"] == 1  # aluno 3 sem turmas

        # Também testa rota via path /tenants/{tenant_id}/students/metrics
        res_tenant = await client.get(f"/tenants/{tenant.id}/students/metrics", headers=headers)
        assert res_tenant.status_code == 200
        assert res_tenant.json()["total_students"] == 3

    async def test_list_students_returns_enriched_metrics(self, client, session):
        """GET /members/students -> Retorna turmas_count, attendance_rate, presenças e status."""
        admin = await UserFactory.create(session)
        aluno1 = await UserFactory.create(session, name="Carlos Silva", email="carlos@test.com")
        aluno2 = await UserFactory.create(session, name="Sem Turma", email="semturma@test.com")

        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin.id, role=UserRole.ADMIN
        )
        m_aluno1 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=aluno1.id, role=UserRole.ALUNO
        )
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=aluno2.id, role=UserRole.ALUNO
        )

        admin_token = create_access_token(
            user_id=admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value
        )
        headers = {"Authorization": f"Bearer {admin_token}"}

        room_res = await client.post(
            "/rooms", json={"name": "Sala C", "latitude": -8.0, "longitude": -34.0}, headers=headers
        )
        room_id = room_res.json()["id"]

        sc_res = await client.post(
            "/subject-classes",
            json={"room_id": room_id, "name": "Turma C", "discipline_name": "Química"},
            headers=headers,
        )
        sc_id = sc_res.json()["id"]

        await client.post(
            f"/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(m_aluno1.id)},
            headers=headers,
        )

        res = await client.get("/members/students", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 2

        carlos = next(i for i in data["items"] if i["name"] == "Carlos Silva")
        assert carlos["turmas_count"] == 1
        assert carlos["status"] == "regular"
        assert carlos["total_sessions"] == 0
        assert carlos["total_present"] == 0
        assert carlos["total_absent"] == 0

        sem_turma = next(i for i in data["items"] if i["name"] == "Sem Turma")
        assert sem_turma["turmas_count"] == 0
        assert sem_turma["status"] == "sem_turma"
