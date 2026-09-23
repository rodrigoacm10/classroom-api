from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from modules.attendance.domain.entities.attendance_record import AttendanceRecord
from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.attendance.infra.repositories.record_sqlalchemy_repository import RecordSQLAlchemyRepository
from modules.attendance.infra.repositories.session_sqlalchemy_repository import SessionSQLAlchemyRepository
from modules.room.domain.entities.room import Room
from modules.room.infra.repositories.room_sqlalchemy_repository import RoomSQLAlchemyRepository
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.infra.repositories.subject_class_sqlalchemy_repository import SubjectClassSQLAlchemyRepository
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ResourceAlreadyExistsException
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestAttendanceSQLAlchemyRepository:

    async def test_save_and_find_attendance_session(self, session):
        """Deve salvar e buscar uma sessão de chamada no banco de dados."""
        tenant = await TenantFactory.create(session)
        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(Room(tenant_id=tenant.id, name="Sala 1", latitude=-8.0, longitude=-34.0))

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="Turma A", discipline_name="Math", room_id=room.id))

        session_repo = SessionSQLAlchemyRepository(session)
        att_session = AttendanceSession(
            subject_class_id=sc.id,
            room_id=room.id,
            day_code="X3KP7Q",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )

        saved = await session_repo.save(att_session)
        assert saved.id is not None
        assert saved.day_code == "X3KP7Q"
        assert saved.status == SessionStatus.OPEN

        found = await session_repo.find_by_id(saved.id)
        assert found is not None
        assert found.id == saved.id

        open_session = await session_repo.find_open_session_by_class(sc.id)
        assert open_session is not None
        assert open_session.id == saved.id

    async def test_create_and_find_attendance_record_with_postgis(self, session):
        """Deve criar um registro de chamada com PostGIS calculando a distância e dentro_do_raio."""
        tenant = await TenantFactory.create(session)
        user = await UserFactory.create(session)
        member = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)

        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(
            Room(tenant_id=tenant.id, name="Lab 1", latitude=-8.047600, longitude=-34.877000, tolerance_radius_meters=50)
        )

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="Turma B", discipline_name="Physics", room_id=room.id))

        session_repo = SessionSQLAlchemyRepository(session)
        att_session = await session_repo.save(
            AttendanceSession(
                subject_class_id=sc.id,
                room_id=room.id,
                day_code="X3KP7Q",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
        )

        record_repo = RecordSQLAlchemyRepository(session)
        record = await record_repo.create_record(
            session_id=att_session.id,
            tenant_member_id=member.id,
            latitude=-8.047610,  # ~15m
            longitude=-34.877010,
            room_id=room.id,
            tolerance_radius_meters=50,
            gps_accuracy_meters=10.0,
            device_id="dev-123",
            user_agent="okhttp/4.9.0",
        )

        assert record.id is not None
        assert record.session_id == att_session.id
        assert record.tenant_member_id == member.id
        assert record.within_radius is True
        assert record.record_status == RecordStatus.REGULAR

        found = await record_repo.find_by_id_and_session(record.id, att_session.id)
        assert found is not None
        assert found.id == record.id

    async def test_create_duplicate_attendance_record_raises_business_rule_exception(self, session):
        """Unique constraint (session_id, tenant_member_id) deve impedir duplicidade e lançar BusinessRuleException."""
        tenant = await TenantFactory.create(session)
        user = await UserFactory.create(session)
        member = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)

        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(Room(tenant_id=tenant.id, name="Lab 1", latitude=-8.0476, longitude=-34.8770))

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="Turma Unique", discipline_name="Test", room_id=room.id))

        session_repo = SessionSQLAlchemyRepository(session)
        att_session = await session_repo.save(
            AttendanceSession(
                subject_class_id=sc.id,
                room_id=room.id,
                day_code="X3KP7Q",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
        )

        record_repo = RecordSQLAlchemyRepository(session)
        await record_repo.create_record(
            session_id=att_session.id,
            tenant_member_id=member.id,
            latitude=-8.047610,
            longitude=-34.877010,
            room_id=room.id,
            tolerance_radius_meters=50,
        )

        with pytest.raises(ResourceAlreadyExistsException, match="Presença já confirmada"):
            await record_repo.create_record(
                session_id=att_session.id,
                tenant_member_id=member.id,
                latitude=-8.047610,
                longitude=-34.877010,
                room_id=room.id,
                tolerance_radius_meters=50,
            )

    async def test_close_expired_sessions_updates_status_in_db(self, session):
        """Deve fechar apenas as sessões de chamada que atingiram o tempo limite de expiração (expires_at <= NOW())."""
        tenant = await TenantFactory.create(session)
        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(Room(tenant_id=tenant.id, name="Sala Expiração", latitude=-8.0, longitude=-34.0))

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="Turma Expiração", discipline_name="Math", room_id=room.id))

        session_repo = SessionSQLAlchemyRepository(session)

        # Sessão 1: Expirou há 10 minutos
        expired_session = await session_repo.save(
            AttendanceSession(
                subject_class_id=sc.id,
                room_id=room.id,
                day_code="EXP123",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            )
        )

        # Sessão 2: Ainda válida (expira em +20 minutos)
        active_session = await session_repo.save(
            AttendanceSession(
                subject_class_id=sc.id,
                room_id=room.id,
                day_code="ACT456",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
            )
        )

        # Executar fecho de expiradas
        closed = await session_repo.close_expired_sessions()
        assert len(closed) == 1
        assert closed[0].id == expired_session.id
        assert closed[0].status == SessionStatus.CLOSED

        # Verificar no PostgreSQL
        reloaded_expired = await session_repo.find_by_id(expired_session.id)
        assert reloaded_expired is not None
        assert reloaded_expired.status == SessionStatus.CLOSED

        reloaded_active = await session_repo.find_by_id(active_session.id)
        assert reloaded_active is not None
        assert reloaded_active.status == SessionStatus.OPEN

    async def test_session_status_pg_enum_labels_are_lowercase_values(self, session):
        """O tipo nativo session_status deve aceitar os values do enum Python, não os names."""
        labels = (
            await session.execute(
                text(
                    """
                    SELECT e.enumlabel
                    FROM pg_enum e
                    JOIN pg_type t ON e.enumtypid = t.oid
                    WHERE t.typname = 'session_status'
                    ORDER BY e.enumsortorder
                    """
                )
            )
        ).scalars().all()

        assert labels == ["open", "closed", "cancelled"]

        accepted = await session.execute(text("SELECT 'open'::session_status::text"))
        assert accepted.scalar_one() == "open"

        cancelled = await session.execute(text("SELECT 'cancelled'::session_status::text"))
        assert cancelled.scalar_one() == "cancelled"

    async def test_session_status_pg_enum_rejects_member_name_open(self, session):
        """
        Reproduz o erro original: invalid input value for enum session_status: "OPEN".
        O SQLAlchemy precisa bindar 'open', porque o Postgres rejeita o name 'OPEN'.
        """
        with pytest.raises(DBAPIError, match='invalid input value for enum session_status: "OPEN"'):
            await session.execute(text("SELECT 'OPEN'::session_status"))

    async def test_find_open_session_persists_and_filters_lowercase_open(self, session):
        """Abrir sessão persiste 'open' e find_open_session_by_class consegue filtrar esse valor."""
        tenant = await TenantFactory.create(session)
        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(Room(tenant_id=tenant.id, name="Sala Enum", latitude=-8.0, longitude=-34.0))

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(
            SubjectClass(tenant_id=tenant.id, name="Turma Enum", discipline_name="Math", room_id=room.id)
        )

        session_repo = SessionSQLAlchemyRepository(session)
        saved = await session_repo.save(
            AttendanceSession(
                subject_class_id=sc.id,
                room_id=room.id,
                day_code="ENUM01",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
        )

        stored = (
            await session.execute(
                text("SELECT status::text FROM attendance_sessions WHERE id = :id"),
                {"id": saved.id},
            )
        ).scalar_one()
        assert stored == "open"

        found = await session_repo.find_open_session_by_class(sc.id)
        assert found is not None
        assert found.id == saved.id
        assert found.status == SessionStatus.OPEN

    async def test_cancelled_session_persists_lowercase_cancelled(self, session):
        """Cancelar sessão deve gravar 'cancelled', valor que a migration adiciona ao enum."""
        tenant = await TenantFactory.create(session)
        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(Room(tenant_id=tenant.id, name="Sala Cancel", latitude=-8.0, longitude=-34.0))

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(
            SubjectClass(tenant_id=tenant.id, name="Turma Cancel", discipline_name="Math", room_id=room.id)
        )

        att_session = AttendanceSession(
            subject_class_id=sc.id,
            room_id=room.id,
            day_code="CANC01",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        att_session.cancel()

        session_repo = SessionSQLAlchemyRepository(session)
        saved = await session_repo.save(att_session)
        assert saved.status == SessionStatus.CANCELLED

        stored = (
            await session.execute(
                text("SELECT status::text FROM attendance_sessions WHERE id = :id"),
                {"id": saved.id},
            )
        ).scalar_one()
        assert stored == "cancelled"

    async def test_session_stats_include_students_confirmed_and_irregular(self, session):
        """GET da sessão agrega duração, alunos ativos, confirmados e irregulares."""
        from modules.enrollment.domain.entities.enrollment import Enrollment
        from modules.enrollment.infra.repositories.enrollment_sqlalchemy_repository import (
            EnrollmentSQLAlchemyRepository,
        )
        from shared.enums.enrollment_status import EnrollmentStatus

        tenant = await TenantFactory.create(session)
        student_a = await UserFactory.create(session, name="Aluno A")
        student_b = await UserFactory.create(session, name="Aluno B")
        student_dropped = await UserFactory.create(session, name="Dropado")
        member_a = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_a.id, role=UserRole.ALUNO
        )
        member_b = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_b.id, role=UserRole.ALUNO
        )
        member_dropped = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_dropped.id, role=UserRole.ALUNO
        )

        room = await RoomSQLAlchemyRepository(session).save(
            Room(tenant_id=tenant.id, name="Lab Stats", latitude=-8.0, longitude=-34.0)
        )
        sc = await SubjectClassSQLAlchemyRepository(session).save(
            SubjectClass(tenant_id=tenant.id, name="POO", discipline_name="Prog", room_id=room.id)
        )
        enrollment_repo = EnrollmentSQLAlchemyRepository(session)
        await enrollment_repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=member_a.id))
        await enrollment_repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=member_b.id))
        await enrollment_repo.save(
            Enrollment(
                subject_class_id=sc.id,
                tenant_member_id=member_dropped.id,
                status=EnrollmentStatus.DROPPED,
            )
        )

        opened_at = datetime.now(timezone.utc)
        att_session = await SessionSQLAlchemyRepository(session).save(
            AttendanceSession(
                subject_class_id=sc.id,
                room_id=room.id,
                day_code="STAT01",
                opened_at=opened_at,
                expires_at=opened_at + timedelta(minutes=20),
            )
        )
        record_repo = RecordSQLAlchemyRepository(session)
        await record_repo.save(
            AttendanceRecord(
                session_id=att_session.id,
                tenant_member_id=member_a.id,
                latitude=-8.0,
                longitude=-34.0,
                distance_meters=3.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            )
        )
        await record_repo.save(
            AttendanceRecord(
                session_id=att_session.id,
                tenant_member_id=member_b.id,
                latitude=-8.0,
                longitude=-34.0,
                distance_meters=80.0,
                within_radius=False,
                record_status=RecordStatus.IRREGULAR,
            )
        )

        found = await SessionSQLAlchemyRepository(session).find_by_id_and_class(
            att_session.id, sc.id
        )
        assert found is not None
        assert found.duration_minutes == 20
        assert found.total_students == 2
        assert found.confirmed_count == 2
        assert found.irregular_count == 1

        listed = await SessionSQLAlchemyRepository(session).list_by_class(sc.id)
        assert len(listed) == 1
        assert listed[0].total_students == 2
        assert listed[0].confirmed_count == 2
        assert listed[0].irregular_count == 1

    async def test_list_session_roster_includes_absent_students_and_attendance_fields(self, session):
        """Roster da chamada lista matriculados ativos com presença opcional; dropados ficam de fora."""
        from modules.enrollment.domain.entities.enrollment import Enrollment
        from modules.enrollment.infra.repositories.enrollment_sqlalchemy_repository import (
            EnrollmentSQLAlchemyRepository,
        )
        from shared.enums.enrollment_status import EnrollmentStatus

        tenant = await TenantFactory.create(session)
        present_user = await UserFactory.create(session, name="Ana Silva")
        absent_user = await UserFactory.create(session, name="Bruno Lima")
        dropped_user = await UserFactory.create(session, name="Carla Souza")
        present_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=present_user.id, role=UserRole.ALUNO
        )
        absent_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=absent_user.id, role=UserRole.ALUNO
        )
        dropped_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=dropped_user.id, role=UserRole.ALUNO
        )

        room = await RoomSQLAlchemyRepository(session).save(
            Room(tenant_id=tenant.id, name="Lab Roster", latitude=-8.0, longitude=-34.0)
        )
        sc = await SubjectClassSQLAlchemyRepository(session).save(
            SubjectClass(tenant_id=tenant.id, name="POO", discipline_name="Prog", room_id=room.id)
        )

        enrollment_repo = EnrollmentSQLAlchemyRepository(session)
        await enrollment_repo.save(
            Enrollment(subject_class_id=sc.id, tenant_member_id=present_member.id)
        )
        await enrollment_repo.save(
            Enrollment(subject_class_id=sc.id, tenant_member_id=absent_member.id)
        )
        await enrollment_repo.save(
            Enrollment(
                subject_class_id=sc.id,
                tenant_member_id=dropped_member.id,
                status=EnrollmentStatus.DROPPED,
            )
        )

        att_session = await SessionSQLAlchemyRepository(session).save(
            AttendanceSession(
                subject_class_id=sc.id,
                room_id=room.id,
                day_code="ROST01",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
        )
        record = await RecordSQLAlchemyRepository(session).save(
            AttendanceRecord(
                session_id=att_session.id,
                tenant_member_id=present_member.id,
                latitude=-8.0,
                longitude=-34.0,
                distance_meters=4.2,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            )
        )

        roster = await RecordSQLAlchemyRepository(session).list_session_roster(
            att_session.id, sc.id
        )
        assert [item.student_name for item in roster] == ["Ana Silva", "Bruno Lima"]

        ana = roster[0]
        assert ana.tenant_member_id == present_member.id
        assert ana.record_id == record.id
        assert ana.confirmed_at is not None
        assert ana.distance_meters == pytest.approx(4.2)
        assert ana.within_radius is True
        assert ana.record_status == RecordStatus.REGULAR

        bruno = roster[1]
        assert bruno.tenant_member_id == absent_member.id
        assert bruno.record_id is None
        assert bruno.confirmed_at is None
        assert bruno.distance_meters is None
        assert bruno.within_radius is None
        assert bruno.record_status is None

    async def test_find_by_class_paginated_with_period_and_status_filters(self, session) -> None:
        """Deve paginar sessões por offset e filtrar por status e período de abertura (opened_at)."""
        from shared.pagination import PaginationParams

        tenant = await TenantFactory.create(session)
        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="História", discipline_name="História"))

        session_repo = SessionSQLAlchemyRepository(session)
        now = datetime.now(timezone.utc)

        s_open = AttendanceSession(
            subject_class_id=sc.id,
            day_code="OPEN01",
            expires_at=now + timedelta(minutes=30),
            opened_at=now - timedelta(hours=1),
            status=SessionStatus.OPEN,
        )
        s_closed = AttendanceSession(
            subject_class_id=sc.id,
            day_code="CLOS01",
            expires_at=now - timedelta(minutes=10),
            opened_at=now - timedelta(days=10),
            status=SessionStatus.CLOSED,
        )
        await session_repo.save(s_open)
        await session_repo.save(s_closed)

        page_all = await session_repo.find_by_class_paginated(
            subject_class_id=sc.id,
            pagination=PaginationParams(page=1, page_size=10),
        )
        assert page_all.total == 2
        assert len(page_all.items) == 2

        page_open = await session_repo.find_by_class_paginated(
            subject_class_id=sc.id,
            pagination=PaginationParams(page=1, page_size=10),
            status=SessionStatus.OPEN,
        )
        assert page_open.total == 1
        assert page_open.items[0].day_code == "OPEN01"

        page_period = await session_repo.find_by_class_paginated(
            subject_class_id=sc.id,
            pagination=PaginationParams(page=1, page_size=10),
            opened_after=now - timedelta(days=1),
        )
        assert page_period.total == 1
        assert page_period.items[0].day_code == "OPEN01"

