from datetime import datetime, timedelta, timezone

import pytest

from infra.database.models.attendance_record import AttendanceRecordModel
from infra.database.models.attendance_session import AttendanceSessionModel
from infra.database.models.enrollment import EnrollmentModel
from infra.database.models.room import RoomModel
from infra.database.models.subject_class import SubjectClassModel
from modules.report.infra.repositories.dashboard_metrics_sqlalchemy_repository import (
    DashboardMetricsSQLAlchemyRepository,
)
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestDashboardMetricsSQLAlchemyRepository:
    async def test_get_metrics_calculates_correctly_for_professor(self, session) -> None:
        """Deve calcular turmas, alunos únicos e taxa de presença dos últimos 30 dias para um professor específico."""
        tenant = await TenantFactory.create(session)

        # Professores
        prof1_user = await UserFactory.create(session, name="Prof 1")
        prof1_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof1_user.id, role=UserRole.PROFESSOR
        )

        prof2_user = await UserFactory.create(session, name="Prof 2")
        prof2_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof2_user.id, role=UserRole.PROFESSOR
        )

        # Alunos
        s1_user = await UserFactory.create(session, name="Aluno 1")
        s1_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=s1_user.id, role=UserRole.ALUNO
        )
        s2_user = await UserFactory.create(session, name="Aluno 2")
        s2_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=s2_user.id, role=UserRole.ALUNO
        )
        s3_user = await UserFactory.create(session, name="Aluno 3")
        s3_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=s3_user.id, role=UserRole.ALUNO
        )

        # Sala
        room = RoomModel(tenant_id=tenant.id, name="Sala 1", location="SRID=4326;POINT(-34.0 -8.0)")
        session.add(room)
        await session.flush()

        # Turmas do Prof 1
        class_a = SubjectClassModel(
            tenant_id=tenant.id,
            professor_id=prof1_member.id,
            room_id=room.id,
            name="Turma A",
            discipline_name="Algoritmos",
            active=True,
        )
        class_b = SubjectClassModel(
            tenant_id=tenant.id,
            professor_id=prof1_member.id,
            room_id=room.id,
            name="Turma B",
            discipline_name="Banco de Dados",
            active=True,
        )
        # Turma do Prof 2
        class_c = SubjectClassModel(
            tenant_id=tenant.id,
            professor_id=prof2_member.id,
            room_id=room.id,
            name="Turma C",
            discipline_name="Redes",
            active=True,
        )
        session.add_all([class_a, class_b, class_c])
        await session.flush()

        # Matrículas
        # Turma A: Aluno 1 e Aluno 2
        e1 = EnrollmentModel(
            subject_class_id=class_a.id,
            tenant_member_id=s1_member.id,
            status=EnrollmentStatus.ACTIVE,
        )
        e2 = EnrollmentModel(
            subject_class_id=class_a.id,
            tenant_member_id=s2_member.id,
            status=EnrollmentStatus.ACTIVE,
        )
        # Turma B: Aluno 2 e Aluno 3 (Aluno 2 está em ambas!)
        e3 = EnrollmentModel(
            subject_class_id=class_b.id,
            tenant_member_id=s2_member.id,
            status=EnrollmentStatus.ACTIVE,
        )
        e4 = EnrollmentModel(
            subject_class_id=class_b.id,
            tenant_member_id=s3_member.id,
            status=EnrollmentStatus.ACTIVE,
        )
        # Turma C (Prof 2): Aluno 3
        e5 = EnrollmentModel(
            subject_class_id=class_c.id,
            tenant_member_id=s3_member.id,
            status=EnrollmentStatus.ACTIVE,
        )
        session.add_all([e1, e2, e3, e4, e5])
        await session.flush()

        # Sessões e Presenças nos últimos 30 dias
        now = datetime.now(timezone.utc)
        # Sessão 1 da Turma A (há 5 dias) -> 2 presentes
        sess1 = AttendanceSessionModel(
            subject_class_id=class_a.id,
            room_id=room.id,
            day_code="1111",
            opened_at=now - timedelta(days=5),
            expires_at=now - timedelta(days=5, minutes=-20),
            status=SessionStatus.CLOSED,
        )
        # Sessão 2 da Turma A (há 10 dias) -> 1 presente (Aluno 1)
        sess2 = AttendanceSessionModel(
            subject_class_id=class_a.id,
            room_id=room.id,
            day_code="2222",
            opened_at=now - timedelta(days=10),
            expires_at=now - timedelta(days=10, minutes=-20),
            status=SessionStatus.CLOSED,
        )
        # Sessão 3 da Turma B (há 2 dias) -> 2 presentes (Aluno 2 e Aluno 3)
        sess3 = AttendanceSessionModel(
            subject_class_id=class_b.id,
            room_id=room.id,
            day_code="3333",
            opened_at=now - timedelta(days=2),
            expires_at=now - timedelta(days=2, minutes=-20),
            status=SessionStatus.CLOSED,
        )
        session.add_all([sess1, sess2, sess3])
        await session.flush()

        # Registros de presença
        rec1 = AttendanceRecordModel(
            session_id=sess1.id,
            tenant_member_id=s1_member.id,
            student_location="SRID=4326;POINT(-34.0 -8.0)",
            distance_meters=10.0,
            within_radius=True,
            record_status=RecordStatus.REGULAR,
        )
        rec2 = AttendanceRecordModel(
            session_id=sess1.id,
            tenant_member_id=s2_member.id,
            student_location="SRID=4326;POINT(-34.0 -8.0)",
            distance_meters=10.0,
            within_radius=True,
            record_status=RecordStatus.REGULAR,
        )
        rec3 = AttendanceRecordModel(
            session_id=sess2.id,
            tenant_member_id=s1_member.id,
            student_location="SRID=4326;POINT(-34.0 -8.0)",
            distance_meters=10.0,
            within_radius=True,
            record_status=RecordStatus.REGULAR,
        )
        rec4 = AttendanceRecordModel(
            session_id=sess3.id,
            tenant_member_id=s2_member.id,
            student_location="SRID=4326;POINT(-34.0 -8.0)",
            distance_meters=10.0,
            within_radius=True,
            record_status=RecordStatus.REGULAR,
        )
        rec5 = AttendanceRecordModel(
            session_id=sess3.id,
            tenant_member_id=s3_member.id,
            student_location="SRID=4326;POINT(-34.0 -8.0)",
            distance_meters=10.0,
            within_radius=True,
            record_status=RecordStatus.APPROVED,
        )
        session.add_all([rec1, rec2, rec3, rec4, rec5])
        await session.flush()

        repo = DashboardMetricsSQLAlchemyRepository(session=session)

        metrics = await repo.get_metrics(
            tenant_id=tenant.id,
            professor_user_id=prof1_user.id,
            active=True,
        )

        assert metrics.total_classes == 2
        # Aluno 1, Aluno 2 e Aluno 3 estão nas turmas do Prof 1 (Aluno 2 em ambas)
        assert metrics.total_unique_students == 3
        # Esperados: Turma A (2 alunos * 2 sessões = 4) + Turma B (2 alunos * 1 sessão = 2) = 6
        # Presentes: 5
        # Taxa: 5 / 6 = 0.8333
        assert metrics.average_attendance_rate == 0.8333
        # Aluno 2 na Turma A tem 1 presença em 2 sessões (50% < 75%) -> em risco
        assert metrics.total_students_at_risk == 1

    async def test_get_metrics_filter_by_active(self, session) -> None:
        """Deve filtrar turmas ativas ou inativas no cálculo das métricas."""
        tenant = await TenantFactory.create(session)
        user = await UserFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN
        )

        class_active = SubjectClassModel(
            tenant_id=tenant.id,
            professor_id=member.id,
            room_id=None,
            name="Ativa",
            discipline_name="D1",
            active=True,
        )
        class_inactive = SubjectClassModel(
            tenant_id=tenant.id,
            professor_id=member.id,
            room_id=None,
            name="Inativa",
            discipline_name="D2",
            active=False,
        )
        session.add_all([class_active, class_inactive])
        await session.flush()

        repo = DashboardMetricsSQLAlchemyRepository(session=session)

        # active=True
        act_metrics = await repo.get_metrics(tenant_id=tenant.id, active=True)
        assert act_metrics.total_classes == 1

        # active=False
        inact_metrics = await repo.get_metrics(tenant_id=tenant.id, active=False)
        assert inact_metrics.total_classes == 1

        # active=None (todas)
        all_metrics = await repo.get_metrics(tenant_id=tenant.id, active=None)
        assert all_metrics.total_classes == 2

    async def test_get_metrics_ignores_sessions_older_than_30_days_and_cancelled(
        self, session
    ) -> None:
        """Deve desconsiderar sessões com mais de 30 dias ou canceladas no cálculo da frequência."""
        tenant = await TenantFactory.create(session)
        user = await UserFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN
        )
        student_user = await UserFactory.create(session)
        student_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_user.id, role=UserRole.ALUNO
        )

        c = SubjectClassModel(
            tenant_id=tenant.id,
            professor_id=member.id,
            room_id=None,
            name="Turma Teste",
            discipline_name="D",
            active=True,
        )
        session.add(c)
        await session.flush()

        e = EnrollmentModel(
            subject_class_id=c.id,
            tenant_member_id=student_member.id,
            status=EnrollmentStatus.ACTIVE,
        )
        session.add(e)
        await session.flush()

        now = datetime.now(timezone.utc)
        # Sessão há 45 dias (antiga)
        old_sess = AttendanceSessionModel(
            subject_class_id=c.id,
            room_id=None,
            day_code="0001",
            opened_at=now - timedelta(days=45),
            expires_at=now - timedelta(days=45, minutes=-20),
            status=SessionStatus.CLOSED,
        )
        # Sessão cancelada
        cancelled_sess = AttendanceSessionModel(
            subject_class_id=c.id,
            room_id=None,
            day_code="0002",
            opened_at=now - timedelta(days=5),
            expires_at=now - timedelta(days=5, minutes=-20),
            status=SessionStatus.CANCELLED,
        )
        session.add_all([old_sess, cancelled_sess])
        await session.flush()

        repo = DashboardMetricsSQLAlchemyRepository(session=session)
        metrics = await repo.get_metrics(tenant_id=tenant.id)

        assert metrics.total_classes == 1
        assert metrics.total_unique_students == 1
        assert metrics.average_attendance_rate == 0.0

    async def test_get_metrics_empty_returns_zeros(self, session) -> None:
        """Deve retornar zeros quando nenhuma turma atender aos critérios."""
        tenant = await TenantFactory.create(session)
        repo = DashboardMetricsSQLAlchemyRepository(session=session)

        metrics = await repo.get_metrics(tenant_id=tenant.id)
        assert metrics.total_classes == 0
        assert metrics.total_unique_students == 0
        assert metrics.average_attendance_rate == 0.0
        assert metrics.total_students_at_risk == 0
        assert len(metrics.week_frequency) == 7
        assert all(d.total_sessions == 0 for d in metrics.week_frequency)
        assert [d.day_label for d in metrics.week_frequency] == [
            "DOM",
            "SEG",
            "TER",
            "QUA",
            "QUI",
            "SEX",
            "SAB",
        ]
        assert metrics.at_risk_students == []

    async def test_get_metrics_calculates_at_risk_students_accurately(self, session) -> None:
        """Deve calcular com precisão a contagem de alunos em risco (< 75%), ignorando turmas sem aulas."""
        tenant = await TenantFactory.create(session)
        user = await UserFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN
        )

        # 3 alunos
        s1 = await UserFactory.create(session)
        m1 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=s1.id, role=UserRole.ALUNO
        )
        s2 = await UserFactory.create(session)
        m2 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=s2.id, role=UserRole.ALUNO
        )
        s3 = await UserFactory.create(session)
        m3 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=s3.id, role=UserRole.ALUNO
        )

        # Turma 1: 4 sessões realizadas
        c1 = SubjectClassModel(
            tenant_id=tenant.id,
            professor_id=member.id,
            room_id=None,
            name="Turma 1",
            discipline_name="Matemática",
            active=True,
        )
        # Turma 2: 0 sessões realizadas (turma recém-criada)
        c2 = SubjectClassModel(
            tenant_id=tenant.id,
            professor_id=member.id,
            room_id=None,
            name="Turma 2",
            discipline_name="Física",
            active=True,
        )
        session.add_all([c1, c2])
        await session.flush()

        # Matrículas
        # m1 em c1 (vai ter 3 presenças / 4 sessões = 75% -> NÃO está em risco)
        # m2 em c1 (vai ter 2 presenças / 4 sessões = 50% < 75% -> ESTÁ em risco)
        # m3 em c1 (vai ter 0 presenças / 4 sessões = 0% < 75% -> ESTÁ em risco)
        # m3 em c2 (turma com 0 sessões -> NÃO deve contar como em risco)
        e1 = EnrollmentModel(
            subject_class_id=c1.id, tenant_member_id=m1.id, status=EnrollmentStatus.ACTIVE
        )
        e2 = EnrollmentModel(
            subject_class_id=c1.id, tenant_member_id=m2.id, status=EnrollmentStatus.ACTIVE
        )
        e3 = EnrollmentModel(
            subject_class_id=c1.id, tenant_member_id=m3.id, status=EnrollmentStatus.ACTIVE
        )
        e4 = EnrollmentModel(
            subject_class_id=c2.id, tenant_member_id=m3.id, status=EnrollmentStatus.ACTIVE
        )
        session.add_all([e1, e2, e3, e4])
        await session.flush()

        now = datetime.now(timezone.utc)
        # 4 sessões em c1
        sessions = [
            AttendanceSessionModel(
                subject_class_id=c1.id,
                room_id=None,
                day_code=f"000{i}",
                opened_at=now - timedelta(days=i + 1),
                expires_at=now - timedelta(days=i + 1, minutes=-20),
                status=SessionStatus.CLOSED,
            )
            for i in range(4)
        ]
        session.add_all(sessions)
        await session.flush()

        # Presenças:
        # m1 presente em 3 sessões (0, 1, 2) -> 3/4 = 75%
        # m2 presente em 2 sessões (0, 1) -> 2/4 = 50%
        # m3 presente em 0 sessões -> 0/4 = 0%
        records = [
            AttendanceRecordModel(
                session_id=sessions[0].id,
                tenant_member_id=m1.id,
                student_location="SRID=4326;POINT(0 0)",
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            ),
            AttendanceRecordModel(
                session_id=sessions[1].id,
                tenant_member_id=m1.id,
                student_location="SRID=4326;POINT(0 0)",
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            ),
            AttendanceRecordModel(
                session_id=sessions[2].id,
                tenant_member_id=m1.id,
                student_location="SRID=4326;POINT(0 0)",
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.APPROVED,
            ),
            AttendanceRecordModel(
                session_id=sessions[0].id,
                tenant_member_id=m2.id,
                student_location="SRID=4326;POINT(0 0)",
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            ),
            AttendanceRecordModel(
                session_id=sessions[1].id,
                tenant_member_id=m2.id,
                student_location="SRID=4326;POINT(0 0)",
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            ),
        ]
        session.add_all(records)
        await session.flush()

        repo = DashboardMetricsSQLAlchemyRepository(session=session)
        metrics = await repo.get_metrics(tenant_id=tenant.id)

        assert metrics.total_classes == 2
        assert metrics.total_unique_students == 3
        # Apenas m2 e m3 na Turma 1 estão em risco (2 matrículas em risco)
        assert metrics.total_students_at_risk == 2

        assert len(metrics.at_risk_students) == 2
        # m3 com 0% vem primeiro que m2 com 50%
        assert metrics.at_risk_students[0].enrollment_id == e3.id
        assert metrics.at_risk_students[0].student_name == s3.name
        assert metrics.at_risk_students[0].class_name == "Turma 1"
        assert metrics.at_risk_students[0].total_sessions == 4
        assert metrics.at_risk_students[0].absences == 4
        assert metrics.at_risk_students[0].attendance_rate == 0.0
        assert metrics.at_risk_students[0].critical is True

        assert metrics.at_risk_students[1].enrollment_id == e2.id
        assert metrics.at_risk_students[1].student_name == s2.name
        assert metrics.at_risk_students[1].class_name == "Turma 1"
        assert metrics.at_risk_students[1].total_sessions == 4
        assert metrics.at_risk_students[1].absences == 2
        assert metrics.at_risk_students[1].attendance_rate == 0.5
        assert metrics.at_risk_students[1].critical is True

    async def test_get_metrics_calculates_week_frequency_sunday_to_saturday(self, session) -> None:
        """Deve calcular a frequência diária agregada de Domingo a Sábado da semana atual."""
        tenant = await TenantFactory.create(session)
        user = await UserFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN
        )

        s1 = await UserFactory.create(session)
        m1 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=s1.id, role=UserRole.ALUNO
        )
        s2 = await UserFactory.create(session)
        m2 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=s2.id, role=UserRole.ALUNO
        )

        # Turma com 2 alunos
        c = SubjectClassModel(
            tenant_id=tenant.id,
            professor_id=member.id,
            room_id=None,
            name="Turma Semana",
            discipline_name="Algoritmos",
            active=True,
        )
        session.add(c)
        await session.flush()

        e1 = EnrollmentModel(
            subject_class_id=c.id, tenant_member_id=m1.id, status=EnrollmentStatus.ACTIVE
        )
        e2 = EnrollmentModel(
            subject_class_id=c.id, tenant_member_id=m2.id, status=EnrollmentStatus.ACTIVE
        )
        session.add_all([e1, e2])
        await session.flush()

        # Semana de referência: Quarta-feira 30/09/2026
        # Domingo = 27/09/2026, Sábado = 03/10/2026
        ref_now = datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc)

        # Sessão 1: Domingo 27/09/2026 -> 2 presentes de 2 esperados (100%)
        sess_dom = AttendanceSessionModel(
            subject_class_id=c.id,
            room_id=None,
            day_code="DOM1",
            opened_at=datetime(2026, 9, 27, 9, 0, 0, tzinfo=timezone.utc),
            expires_at=datetime(2026, 9, 27, 9, 20, 0, tzinfo=timezone.utc),
            status=SessionStatus.CLOSED,
        )
        # Sessão 2: Terça 29/09/2026 -> 1 presente de 2 esperados (50%)
        sess_ter = AttendanceSessionModel(
            subject_class_id=c.id,
            room_id=None,
            day_code="TER1",
            opened_at=datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc),
            expires_at=datetime(2026, 9, 29, 10, 20, 0, tzinfo=timezone.utc),
            status=SessionStatus.CLOSED,
        )
        # Sessão 3: Quarta 30/09/2026 (Cancelada) -> deve ser ignorada
        sess_qua_canc = AttendanceSessionModel(
            subject_class_id=c.id,
            room_id=None,
            day_code="QUA1",
            opened_at=datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc),
            expires_at=datetime(2026, 9, 30, 14, 20, 0, tzinfo=timezone.utc),
            status=SessionStatus.CANCELLED,
        )
        # Sessão 4: Sexta 02/10/2026 -> 0 presentes de 2 esperados (0%)
        sess_sex = AttendanceSessionModel(
            subject_class_id=c.id,
            room_id=None,
            day_code="SEX1",
            opened_at=datetime(2026, 10, 2, 8, 0, 0, tzinfo=timezone.utc),
            expires_at=datetime(2026, 10, 2, 8, 20, 0, tzinfo=timezone.utc),
            status=SessionStatus.CLOSED,
        )
        # Sessão 5: Sábado 03/10/2026 -> 2 presentes de 2 esperados (100%)
        sess_sab = AttendanceSessionModel(
            subject_class_id=c.id,
            room_id=None,
            day_code="SAB1",
            opened_at=datetime(2026, 10, 3, 11, 0, 0, tzinfo=timezone.utc),
            expires_at=datetime(2026, 10, 3, 11, 20, 0, tzinfo=timezone.utc),
            status=SessionStatus.CLOSED,
        )
        # Sessão 6: Fora da semana (Domingo anterior 20/09/2026) -> deve ser ignorada
        sess_old = AttendanceSessionModel(
            subject_class_id=c.id,
            room_id=None,
            day_code="OLD1",
            opened_at=datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc),
            expires_at=datetime(2026, 9, 20, 10, 20, 0, tzinfo=timezone.utc),
            status=SessionStatus.CLOSED,
        )
        session.add_all([sess_dom, sess_ter, sess_qua_canc, sess_sex, sess_sab, sess_old])
        await session.flush()

        # Registros de presença
        records = [
            # Domingo: m1 e m2 presentes
            AttendanceRecordModel(
                session_id=sess_dom.id,
                tenant_member_id=m1.id,
                student_location="SRID=4326;POINT(0 0)",
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            ),
            AttendanceRecordModel(
                session_id=sess_dom.id,
                tenant_member_id=m2.id,
                student_location="SRID=4326;POINT(0 0)",
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.APPROVED,
            ),
            # Terça: apenas m1 presente
            AttendanceRecordModel(
                session_id=sess_ter.id,
                tenant_member_id=m1.id,
                student_location="SRID=4326;POINT(0 0)",
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            ),
            # Sábado: m1 e m2 presentes
            AttendanceRecordModel(
                session_id=sess_sab.id,
                tenant_member_id=m1.id,
                student_location="SRID=4326;POINT(0 0)",
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            ),
            AttendanceRecordModel(
                session_id=sess_sab.id,
                tenant_member_id=m2.id,
                student_location="SRID=4326;POINT(0 0)",
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            ),
        ]
        session.add_all(records)
        await session.flush()

        repo = DashboardMetricsSQLAlchemyRepository(session=session)
        metrics = await repo.get_metrics(tenant_id=tenant.id, now=ref_now)

        assert len(metrics.week_frequency) == 7
        labels = [d.day_label for d in metrics.week_frequency]
        assert labels == ["DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SAB"]

        dom = metrics.week_frequency[0]
        assert dom.day_label == "DOM"
        assert dom.date == "2026-09-27"
        assert dom.total_sessions == 1
        assert dom.total_expected == 2
        assert dom.total_presents == 2
        assert dom.attendance_rate == 1.0

        seg = metrics.week_frequency[1]
        assert seg.day_label == "SEG"
        assert seg.date == "2026-09-28"
        assert seg.total_sessions == 0
        assert seg.attendance_rate == 0.0

        ter = metrics.week_frequency[2]
        assert ter.day_label == "TER"
        assert ter.date == "2026-09-29"
        assert ter.total_sessions == 1
        assert ter.total_expected == 2
        assert ter.total_presents == 1
        assert ter.attendance_rate == 0.5

        qua = metrics.week_frequency[3]
        assert qua.day_label == "QUA"
        assert qua.date == "2026-09-30"
        # Sessão cancelada não é contabilizada
        assert qua.total_sessions == 0
        assert qua.attendance_rate == 0.0

        qui = metrics.week_frequency[4]
        assert qui.day_label == "QUI"
        assert qui.date == "2026-10-01"
        assert qui.total_sessions == 0

        sex = metrics.week_frequency[5]
        assert sex.day_label == "SEX"
        assert sex.date == "2026-10-02"
        assert sex.total_sessions == 1
        assert sex.total_expected == 2
        assert sex.total_presents == 0
        assert sex.attendance_rate == 0.0

        sab = metrics.week_frequency[6]
        assert sab.day_label == "SAB"
        assert sab.date == "2026-10-03"
        assert sab.total_sessions == 1
        assert sab.total_expected == 2
        assert sab.total_presents == 2
        assert sab.attendance_rate == 1.0
