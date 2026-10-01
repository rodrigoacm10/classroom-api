import pytest

from security.jwt import create_access_token
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestActiveAttendanceSessionsRouter:
    async def _setup_fixtures(self, session, client):
        # 1. Admin
        admin_user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin_user.id, role=UserRole.ADMIN
        )
        admin_token = create_access_token(
            user_id=admin_user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value
        )
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 2. Prof 1
        prof1_user = await UserFactory.create(session, name="Professora Ana")
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof1_user.id, role=UserRole.PROFESSOR
        )
        prof1_token = create_access_token(
            user_id=prof1_user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value
        )
        prof1_headers = {"Authorization": f"Bearer {prof1_token}"}

        # 3. Prof 2
        prof2_user = await UserFactory.create(session, name="Professor Carlos")
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof2_user.id, role=UserRole.PROFESSOR
        )
        prof2_token = create_access_token(
            user_id=prof2_user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value
        )
        prof2_headers = {"Authorization": f"Bearer {prof2_token}"}

        # 4. Aluno
        student_user = await UserFactory.create(session, name="Lucas Mendes")
        student_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_user.id, role=UserRole.ALUNO
        )
        student_token = create_access_token(
            user_id=student_user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value
        )
        student_headers = {"Authorization": f"Bearer {student_token}"}

        # 5. Salas
        room1_res = await client.post(
            "/rooms",
            json={"name": "Lab 204", "latitude": -8.0476, "longitude": -34.8770},
            headers=admin_headers,
        )
        room1_id = room1_res.json()["id"]

        room2_res = await client.post(
            "/rooms",
            json={"name": "Sala 12", "latitude": -8.0476, "longitude": -34.8770},
            headers=admin_headers,
        )
        room2_id = room2_res.json()["id"]

        # 6. Turma 1 (Prof 1)
        sc1_res = await client.post(
            "/subject-classes",
            json={
                "room_id": room1_id,
                "name": "T01",
                "discipline_name": "Algoritmos e Estruturas de Dados",
            },
            headers=prof1_headers,
        )
        sc1_id = sc1_res.json()["id"]

        # 7. Turma 2 (Prof 2)
        sc2_res = await client.post(
            "/subject-classes",
            json={
                "room_id": room2_id,
                "name": "T02",
                "discipline_name": "Banco de Dados",
            },
            headers=prof2_headers,
        )
        sc2_id = sc2_res.json()["id"]

        # 8. Matricula aluno na Turma 1
        await client.post(
            f"/subject-classes/{sc1_id}/enrollments",
            json={"tenant_member_id": str(student_member.id)},
            headers=prof1_headers,
        )

        return (
            tenant,
            admin_headers,
            prof1_headers,
            prof2_headers,
            student_headers,
            sc1_id,
            sc2_id,
            room1_id,
            student_member,
        )

    async def test_professor_sees_only_his_active_sessions(self, client, session):
        """GET /attendance-sessions/active -> Professor só vê as chamadas das suas turmas."""
        (
            tenant,
            admin_headers,
            prof1_headers,
            prof2_headers,
            student_headers,
            sc1_id,
            sc2_id,
            room1_id,
            student_member,
        ) = await self._setup_fixtures(session, client)

        # Abre chamada na Turma 1 (Prof 1)
        res1 = await client.post(
            f"/subject-classes/{sc1_id}/attendance-sessions",
            json={"room_id": room1_id, "duration_minutes": 25},
            headers=prof1_headers,
        )
        assert res1.status_code == 201
        session1_data = res1.json()

        # Abre chamada na Turma 2 (Prof 2)
        res2 = await client.post(
            f"/subject-classes/{sc2_id}/attendance-sessions",
            json={"duration_minutes": 30},
            headers=prof2_headers,
        )
        assert res2.status_code == 201

        # Aluno confirma presença na chamada da Turma 1
        confirm_res = await client.post(
            f"/subject-classes/{sc1_id}/attendance-sessions/{session1_data['id']}/confirm",
            json={
                "day_code": session1_data["day_code"],
                "latitude": -8.0476,
                "longitude": -34.8770,
                "gps_accuracy_meters": 5.0,
            },
            headers=student_headers,
        )
        assert confirm_res.status_code == 201

        # Prof 1 consulta chamadas ativas
        get_res = await client.get("/attendance-sessions/active", headers=prof1_headers)
        assert get_res.status_code == 200
        active_list = get_res.json()

        # Deve conter apenas a sessão da Turma 1
        assert len(active_list) == 1
        item = active_list[0]
        assert item["session_id"] == session1_data["id"]
        assert item["subject_class_id"] == sc1_id
        assert item["subject_class_name"] == "T01"
        assert item["discipline_name"] == "Algoritmos e Estruturas de Dados"
        assert item["day_code"] == session1_data["day_code"]
        assert item["room_name"] == "Lab 204"
        assert item["duration_minutes"] == 25
        assert item["present_count"] == 1
        assert item["total_students"] == 1
        assert "opened_at" in item
        assert "expires_at" in item

    async def test_admin_sees_all_active_sessions_in_tenant(self, client, session):
        """GET /attendance-sessions/active -> Admin vê as chamadas de todas as turmas do tenant."""
        (
            tenant,
            admin_headers,
            prof1_headers,
            prof2_headers,
            _,
            sc1_id,
            sc2_id,
            room1_id,
            _,
        ) = await self._setup_fixtures(session, client)

        # Abre chamada na Turma 1 (Prof 1)
        await client.post(
            f"/subject-classes/{sc1_id}/attendance-sessions",
            json={"room_id": room1_id, "duration_minutes": 15},
            headers=prof1_headers,
        )

        # Abre chamada na Turma 2 (Prof 2)
        await client.post(
            f"/subject-classes/{sc2_id}/attendance-sessions",
            json={"duration_minutes": 20},
            headers=prof2_headers,
        )

        # Admin consulta
        get_res = await client.get("/attendance-sessions/active", headers=admin_headers)
        assert get_res.status_code == 200
        active_list = get_res.json()
        assert len(active_list) == 2

    async def test_closed_session_does_not_appear_in_active_list(self, client, session):
        """GET /attendance-sessions/active -> Sessões encerradas não aparecem na listagem."""
        (
            tenant,
            admin_headers,
            prof1_headers,
            _,
            _,
            sc1_id,
            _,
            room1_id,
            _,
        ) = await self._setup_fixtures(session, client)

        # Abre chamada
        open_res = await client.post(
            f"/subject-classes/{sc1_id}/attendance-sessions",
            json={"room_id": room1_id, "duration_minutes": 15},
            headers=prof1_headers,
        )
        s_id = open_res.json()["id"]

        # Fecha a chamada
        close_res = await client.patch(
            f"/subject-classes/{sc1_id}/attendance-sessions/{s_id}/close",
            headers=prof1_headers,
        )
        assert close_res.status_code == 200

        # Consulta ativas
        get_res = await client.get("/attendance-sessions/active", headers=prof1_headers)
        assert get_res.status_code == 200
        assert len(get_res.json()) == 0

    async def test_student_cannot_access_active_sessions(self, client, session):
        """GET /attendance-sessions/active -> Aluno recebe 403 Forbidden."""
        (
            tenant,
            _,
            _,
            _,
            student_headers,
            _,
            _,
            _,
            _,
        ) = await self._setup_fixtures(session, client)

        res = await client.get("/attendance-sessions/active", headers=student_headers)
        assert res.status_code == 403
