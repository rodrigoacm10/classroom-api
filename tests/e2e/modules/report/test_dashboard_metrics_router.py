from datetime import datetime, timedelta, timezone

import pytest

from infra.database.models.attendance_record import AttendanceRecordModel
from infra.database.models.attendance_session import AttendanceSessionModel
from infra.database.models.enrollment import EnrollmentModel
from infra.database.models.room import RoomModel
from infra.database.models.subject_class import SubjectClassModel
from security.jwt import create_access_token
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestDashboardMetricsRouter:
    async def _setup_data(self, session):
        tenant = await TenantFactory.create(session)

        # 1. Admin
        admin_user = await UserFactory.create(session, name="Admin")
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin_user.id, role=UserRole.ADMIN
        )
        admin_token = create_access_token(
            user_id=admin_user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value
        )
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 2. Prof 1 (Ana)
        prof1_user = await UserFactory.create(session, name="Ana")
        prof1_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof1_user.id, role=UserRole.PROFESSOR
        )
        prof1_token = create_access_token(
            user_id=prof1_user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value
        )
        prof1_headers = {"Authorization": f"Bearer {prof1_token}"}

        # 3. Prof 2 (Carlos)
        prof2_user = await UserFactory.create(session, name="Carlos")
        prof2_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof2_user.id, role=UserRole.PROFESSOR
        )
        prof2_token = create_access_token(
            user_id=prof2_user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value
        )
        prof2_headers = {"Authorization": f"Bearer {prof2_token}"}

        # 4. Aluno (Lucas)
        student_user = await UserFactory.create(session, name="Lucas")
        student_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_user.id, role=UserRole.ALUNO
        )
        student_token = create_access_token(
            user_id=student_user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value
        )
        student_headers = {"Authorization": f"Bearer {student_token}"}

        # 5. Outro Aluno (Mariana)
        student2_user = await UserFactory.create(session, name="Mariana")
        student2_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student2_user.id, role=UserRole.ALUNO
        )

        # Sala
        room = RoomModel(
            tenant_id=tenant.id, name="Lab 101", location="SRID=4326;POINT(-34.0 -8.0)"
        )
        session.add(room)
        await session.flush()

        # Turmas da Professora Ana (1 ativa e 1 inativa)
        class_ana_act = SubjectClassModel(
            tenant_id=tenant.id,
            professor_id=prof1_member.id,
            room_id=room.id,
            name="Turma Ana Ativa",
            discipline_name="Algoritmos",
            active=True,
        )
        class_ana_inact = SubjectClassModel(
            tenant_id=tenant.id,
            professor_id=prof1_member.id,
            room_id=room.id,
            name="Turma Ana Inativa",
            discipline_name="Matemática",
            active=False,
        )

        # Turma do Professor Carlos (1 ativa)
        class_carlos_act = SubjectClassModel(
            tenant_id=tenant.id,
            professor_id=prof2_member.id,
            room_id=room.id,
            name="Turma Carlos Ativa",
            discipline_name="Redes",
            active=True,
        )
        session.add_all([class_ana_act, class_ana_inact, class_carlos_act])
        await session.flush()

        # Matrículas
        # Lucas na Turma Ana Ativa
        e1 = EnrollmentModel(
            subject_class_id=class_ana_act.id,
            tenant_member_id=student_member.id,
            status=EnrollmentStatus.ACTIVE,
        )
        # Mariana na Turma Ana Ativa
        e2 = EnrollmentModel(
            subject_class_id=class_ana_act.id,
            tenant_member_id=student2_member.id,
            status=EnrollmentStatus.ACTIVE,
        )
        # Lucas também na Turma Carlos Ativa
        e3 = EnrollmentModel(
            subject_class_id=class_carlos_act.id,
            tenant_member_id=student_member.id,
            status=EnrollmentStatus.ACTIVE,
        )
        session.add_all([e1, e2, e3])
        await session.flush()

        # Chamada na Turma Ana Ativa (há 2 dias) -> 2 presentes
        now = datetime.now(timezone.utc)
        sess_ana = AttendanceSessionModel(
            subject_class_id=class_ana_act.id,
            room_id=room.id,
            day_code="7777",
            opened_at=now - timedelta(days=2),
            expires_at=now - timedelta(days=2, minutes=-20),
            status=SessionStatus.CLOSED,
        )
        session.add(sess_ana)
        await session.flush()

        rec1 = AttendanceRecordModel(
            session_id=sess_ana.id,
            tenant_member_id=student_member.id,
            student_location="SRID=4326;POINT(-34.0 -8.0)",
            distance_meters=5.0,
            within_radius=True,
            record_status=RecordStatus.REGULAR,
        )
        rec2 = AttendanceRecordModel(
            session_id=sess_ana.id,
            tenant_member_id=student2_member.id,
            student_location="SRID=4326;POINT(-34.0 -8.0)",
            distance_meters=5.0,
            within_radius=True,
            record_status=RecordStatus.REGULAR,
        )
        session.add_all([rec1, rec2])
        await session.flush()

        return {
            "tenant": tenant,
            "admin_headers": admin_headers,
            "prof1_headers": prof1_headers,
            "prof2_headers": prof2_headers,
            "student_headers": student_headers,
            "class_ana_act": class_ana_act,
            "student_member": student_member,
            "student2_member": student2_member,
            "room": room,
        }

    async def test_professor_sees_only_own_dashboard_metrics(self, client, session) -> None:
        """GET /dashboard/metrics -> Professor visualiza apenas métricas consolidadas das suas próprias turmas."""
        data = await self._setup_data(session)

        res = await client.get("/dashboard/metrics?active=true", headers=data["prof1_headers"])
        assert res.status_code == 200
        metrics = res.json()

        # Ana possui apenas 1 turma ativa
        assert metrics["total_classes"] == 1
        # Lucas e Mariana estão matriculados nessa turma ativa
        assert metrics["total_unique_students"] == 2
        # 2 presentes de 2 esperados = 1.0 (100%)
        assert metrics["average_attendance_rate"] == 1.0
        # Nenhum aluno com < 75% de presença
        assert metrics["total_students_at_risk"] == 0
        assert len(metrics["week_frequency"]) == 7
        assert [d["day_label"] for d in metrics["week_frequency"]] == [
            "DOM",
            "SEG",
            "TER",
            "QUA",
            "QUI",
            "SEX",
            "SAB",
        ]
        assert metrics["at_risk_students"] == []

    async def test_admin_sees_all_tenant_metrics(self, client, session) -> None:
        """GET /dashboard/metrics -> Administrador visualiza métricas de todas as turmas do tenant."""
        data = await self._setup_data(session)

        res = await client.get("/dashboard/metrics?active=true", headers=data["admin_headers"])
        assert res.status_code == 200
        metrics = res.json()

        # Total de turmas ativas no tenant: Ana (1) + Carlos (1) = 2
        assert metrics["total_classes"] == 2
        # Alunos únicos ativos: Lucas e Mariana (Lucas está em ambas as turmas)
        assert metrics["total_unique_students"] == 2

    async def test_filter_by_active_query_param(self, client, session) -> None:
        """GET /dashboard/metrics?active=true|false deve filtrar métricas por status da turma."""
        data = await self._setup_data(session)

        # active=true para Ana: 1 turma
        res_act = await client.get("/dashboard/metrics?active=true", headers=data["prof1_headers"])
        assert res_act.status_code == 200
        assert res_act.json()["total_classes"] == 1

        # active=false para Ana: 1 turma inativa
        res_inact = await client.get(
            "/dashboard/metrics?active=false", headers=data["prof1_headers"]
        )
        assert res_inact.status_code == 200
        assert res_inact.json()["total_classes"] == 1

        # sem parâmetro active para Ana: 2 turmas
        res_all = await client.get("/dashboard/metrics", headers=data["prof1_headers"])
        assert res_all.status_code == 200
        assert res_all.json()["total_classes"] == 2

    async def test_student_role_forbidden(self, client, session) -> None:
        """GET /dashboard/metrics -> Papel ALUNO deve receber 403 Forbidden."""
        data = await self._setup_data(session)

        res = await client.get("/dashboard/metrics", headers=data["student_headers"])
        assert res.status_code == 403

    async def test_dashboard_metrics_returns_at_risk_students_count(self, client, session) -> None:
        """GET /dashboard/metrics deve retornar a contagem correta de alunos em risco (< 75%)."""
        data = await self._setup_data(session)

        # Adiciona uma segunda sessão na turma da Professora Ana
        # Apenas Mariana estará presente na segunda sessão. Lucas terá 1 falta (1/2 = 50% < 75% -> risco)
        now = datetime.now(timezone.utc)
        sess2 = AttendanceSessionModel(
            subject_class_id=data["class_ana_act"].id,
            room_id=data["room"].id,
            day_code="8888",
            opened_at=now - timedelta(days=1),
            expires_at=now - timedelta(days=1, minutes=-20),
            status=SessionStatus.CLOSED,
        )
        session.add(sess2)
        await session.flush()

        rec_mariana = AttendanceRecordModel(
            session_id=sess2.id,
            tenant_member_id=data["student2_member"].id,
            student_location="SRID=4326;POINT(-34.0 -8.0)",
            distance_meters=5.0,
            within_radius=True,
            record_status=RecordStatus.REGULAR,
        )
        session.add(rec_mariana)
        await session.flush()

        res = await client.get("/dashboard/metrics?active=true", headers=data["prof1_headers"])
        assert res.status_code == 200
        metrics = res.json()

        assert metrics["total_classes"] == 1
        assert metrics["total_unique_students"] == 2
        # Lucas tem 1 presença em 2 sessões (50% < 75%) -> 1 aluno em risco
        assert metrics["total_students_at_risk"] == 1

        assert len(metrics["at_risk_students"]) == 1
        lucas_risk = metrics["at_risk_students"][0]
        assert lucas_risk["student_name"] == "Lucas"
        assert lucas_risk["class_name"] == "Turma Ana Ativa"
        assert lucas_risk["total_sessions"] == 2
        assert lucas_risk["absences"] == 1
        assert lucas_risk["attendance_rate"] == 0.5
        assert lucas_risk["critical"] is True
