from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.attendance.application.use_cases.list_session_roster import (
    ListSessionRosterInput,
    ListSessionRosterUseCase,
)
from modules.attendance.domain.entities.attendance_record import AttendanceRecord
from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.subject_class.domain.entities.subject_class import SubjectClass
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.exceptions import ResourceNotFoundException
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_attendance_record_repository import FakeAttendanceRecordRepository
from tests.unit.fakes.fake_attendance_session_repository import FakeAttendanceSessionRepository
from tests.unit.fakes.fake_subject_class_repository import FakeSubjectClassRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestListSessionRosterUseCase:

    async def _setup(self):
        session_repo = FakeAttendanceSessionRepository()
        record_repo = FakeAttendanceRecordRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma POO",
            discipline_name="POO",
        )
        await subject_class_repo.save(subject_class)

        att_session = AttendanceSession(
            subject_class_id=subject_class.id,
            day_code="ABC123",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            status=SessionStatus.OPEN,
        )
        await session_repo.save(att_session)

        use_case = ListSessionRosterUseCase(
            record_repo=record_repo,
            session_repo=session_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
        )
        return tenant, subject_class, att_session, record_repo, use_case

    async def test_lists_enrolled_students_with_and_without_attendance(self):
        """Deve listar todos os matriculados, preenchendo horário/distância/status só de quem marcou."""
        tenant, subject_class, att_session, record_repo, use_case = await self._setup()

        present_id = uuid4()
        absent_id = uuid4()
        record_repo.seed_enrolled_student(subject_class.id, present_id, "Ana")
        record_repo.seed_enrolled_student(subject_class.id, absent_id, "Bruno")

        record = AttendanceRecord(
            session_id=att_session.id,
            tenant_member_id=present_id,
            latitude=-8.0,
            longitude=-34.0,
            distance_meters=12.5,
            within_radius=True,
            record_status=RecordStatus.REGULAR,
        )
        await record_repo.save(record)

        result = await use_case.execute(
            ListSessionRosterInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                session_id=att_session.id,
            )
        )

        assert len(result) == 2
        by_name = {item.student_name: item for item in result}

        ana = by_name["Ana"]
        assert ana.tenant_member_id == present_id
        assert ana.record_id == record.id
        assert ana.confirmed_at == record.confirmed_at
        assert ana.distance_meters == 12.5
        assert ana.within_radius is True
        assert ana.record_status == RecordStatus.REGULAR

        bruno = by_name["Bruno"]
        assert bruno.tenant_member_id == absent_id
        assert bruno.record_id is None
        assert bruno.confirmed_at is None
        assert bruno.distance_meters is None
        assert bruno.within_radius is None
        assert bruno.record_status is None

    async def test_tenant_not_found(self):
        _, subject_class, att_session, _, use_case = await self._setup()
        with pytest.raises(ResourceNotFoundException, match="Instituição/tenant não encontrada."):
            await use_case.execute(
                ListSessionRosterInput(
                    tenant_id=uuid4(),
                    subject_class_id=subject_class.id,
                    session_id=att_session.id,
                )
            )

    async def test_subject_class_not_found(self):
        tenant, _, att_session, _, use_case = await self._setup()
        with pytest.raises(ResourceNotFoundException, match="Turma não encontrada."):
            await use_case.execute(
                ListSessionRosterInput(
                    tenant_id=tenant.id,
                    subject_class_id=uuid4(),
                    session_id=att_session.id,
                )
            )

    async def test_session_not_found(self):
        tenant, subject_class, _, _, use_case = await self._setup()
        with pytest.raises(ResourceNotFoundException, match="Sessão de chamada não encontrada."):
            await use_case.execute(
                ListSessionRosterInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    session_id=uuid4(),
                )
            )
