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

