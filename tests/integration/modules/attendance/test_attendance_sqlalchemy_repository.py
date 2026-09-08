from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

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
