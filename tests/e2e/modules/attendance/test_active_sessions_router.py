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

    async def test_list_attendance_sessions_by_tenant(self, client, session):
        """GET /attendance-sessions -> Lista sessões paginadas de todas as turmas do tenant/professor."""
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

        # Prof 1 abre chamada
        await client.post(
            f"/subject-classes/{sc1_id}/attendance-sessions",
            json={"room_id": room1_id, "duration_minutes": 15},
            headers=prof1_headers,
        )

        # Prof 2 abre chamada
        await client.post(
            f"/subject-classes/{sc2_id}/attendance-sessions",
            json={"room_id": room1_id, "duration_minutes": 20},
            headers=prof2_headers,
        )

        # Prof 1 consulta: só deve ver 1
        p1_res = await client.get("/attendance-sessions", headers=prof1_headers)
        assert p1_res.status_code == 200
        p1_data = p1_res.json()
        assert p1_data["total"] == 1
        assert len(p1_data["items"]) == 1
        assert p1_data["items"][0]["subject_class_id"] == str(sc1_id)

        # Admin consulta: deve ver ambas
        admin_res = await client.get("/attendance-sessions", headers=admin_headers)
        assert admin_res.status_code == 200
        admin_data = admin_res.json()
        assert admin_data["total"] == 2
        assert len(admin_data["items"]) == 2

    async def test_get_attendance_metrics(self, client, session):
        """GET /attendance-sessions/metrics -> Retorna métricas dos últimos 30 dias e última chamada."""
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

        # Abre chamada 1 e fecha
        s1 = (
            await client.post(
                f"/subject-classes/{sc1_id}/attendance-sessions",
                json={"room_id": room1_id, "duration_minutes": 15},
                headers=prof1_headers,
            )
        ).json()
        await client.patch(
            f"/subject-classes/{sc1_id}/attendance-sessions/{s1['id']}/close",
            headers=prof1_headers,
        )

        # Consulta métricas
        metrics_res = await client.get("/attendance-sessions/metrics?days=30", headers=prof1_headers)
        assert metrics_res.status_code == 200
        metrics = metrics_res.json()
        assert metrics["total_sessions"] == 1
        assert metrics["cancelled_sessions"] == 0
        assert metrics["last_session"] is not None
        assert metrics["last_session"]["id"] == s1["id"]
        assert metrics["last_session"]["subject_class_id"] == str(sc1_id)

    async def test_student_cannot_access_tenant_sessions_or_metrics(self, client, session):
        """Alunos não têm permissão para acessar GET /attendance-sessions ou GET /attendance-sessions/metrics."""
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

        res1 = await client.get("/attendance-sessions", headers=student_headers)
        assert res1.status_code == 403

        res2 = await client.get("/attendance-sessions/metrics", headers=student_headers)
        assert res2.status_code == 403

    async def test_metrics_cancelled_sessions_and_role_isolation(self, client, session):
        """Métricas registram sessões canceladas e respeitam isolamento de professor vs admin."""
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

        # Prof 1 abre chamada e cancela
        s1 = (
            await client.post(
                f"/subject-classes/{sc1_id}/attendance-sessions",
                json={"room_id": room1_id, "duration_minutes": 15},
                headers=prof1_headers,
            )
        ).json()
        cancel_res = await client.patch(
            f"/subject-classes/{sc1_id}/attendance-sessions/{s1['id']}/cancel",
            headers=prof1_headers,
        )
        assert cancel_res.status_code == 200

        # Prof 2 abre chamada e encerra
        s2 = (
            await client.post(
                f"/subject-classes/{sc2_id}/attendance-sessions",
                json={"room_id": room1_id, "duration_minutes": 20},
                headers=prof2_headers,
            )
        ).json()
        await client.patch(
            f"/subject-classes/{sc2_id}/attendance-sessions/{s2['id']}/close",
            headers=prof2_headers,
        )

        # Prof 1 vê apenas a sua chamada (1 total, 1 cancelada)
        p1_res = await client.get("/attendance-sessions/metrics?days=30", headers=prof1_headers)
        assert p1_res.status_code == 200
        p1_metrics = p1_res.json()
        assert p1_metrics["total_sessions"] == 1
        assert p1_metrics["cancelled_sessions"] == 1
        assert p1_metrics["last_session"]["id"] == s1["id"]

        # Prof 2 vê apenas a sua chamada (1 total, 0 canceladas)
        p2_res = await client.get("/attendance-sessions/metrics?days=30", headers=prof2_headers)
        assert p2_res.status_code == 200
        p2_metrics = p2_res.json()
        assert p2_metrics["total_sessions"] == 1
        assert p2_metrics["cancelled_sessions"] == 0
        assert p2_metrics["last_session"]["id"] == s2["id"]

        # Admin vê o consolidado de todas as turmas (2 total, 1 cancelada)
        admin_res = await client.get("/attendance-sessions/metrics?days=30", headers=admin_headers)
        assert admin_res.status_code == 200
        admin_metrics = admin_res.json()
        assert admin_metrics["total_sessions"] == 2
        assert admin_metrics["cancelled_sessions"] == 1

    async def test_list_attendance_sessions_search_and_filters(self, client, session):
        """GET /attendance-sessions suporta filtros por busca de disciplina e por status."""
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

        # Prof 1 cria chamada (Algoritmos) e fecha
        s1 = (
            await client.post(
                f"/subject-classes/{sc1_id}/attendance-sessions",
                json={"room_id": room1_id, "duration_minutes": 15},
                headers=prof1_headers,
            )
        ).json()
        await client.patch(
            f"/subject-classes/{sc1_id}/attendance-sessions/{s1['id']}/close",
            headers=prof1_headers,
        )

        # Prof 2 cria chamada (Banco de Dados) e deixa aberta
        await client.post(
            f"/subject-classes/{sc2_id}/attendance-sessions",
            json={"room_id": room1_id, "duration_minutes": 30},
            headers=prof2_headers,
        )

        # Busca por "Algoritmos" via Admin
        res_search = await client.get("/attendance-sessions?search=Algoritmos", headers=admin_headers)
        assert res_search.status_code == 200
        data_search = res_search.json()
        assert data_search["total"] == 1
        assert data_search["items"][0]["subject_class"]["discipline_name"] == "Algoritmos e Estruturas de Dados"

        # Filtro por status closed
        res_closed = await client.get("/attendance-sessions?status=closed", headers=admin_headers)
        assert res_closed.status_code == 200
        data_closed = res_closed.json()
        assert data_closed["total"] == 1
        assert data_closed["items"][0]["id"] == s1["id"]

        # Filtro por status open (Em andamento)
        res_open = await client.get("/attendance-sessions?status=open", headers=admin_headers)
        assert res_open.status_code == 200
        data_open = res_open.json()
        assert data_open["total"] == 1
        assert data_open["items"][0]["status"] == "open"

        # Excluir status open (Apenas realizadas / finalizadas)
        res_exclude = await client.get("/attendance-sessions?exclude_status=open", headers=admin_headers)
        assert res_exclude.status_code == 200
        data_exclude = res_exclude.json()
        assert data_exclude["total"] == 1
        assert data_exclude["items"][0]["status"] == "closed"

