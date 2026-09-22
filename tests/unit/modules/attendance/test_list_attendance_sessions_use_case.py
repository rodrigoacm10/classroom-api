from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.attendance.application.use_cases.list_sessions import (
    ListAttendanceSessionsInput,
    ListAttendanceSessionsUseCase,
)
from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.subject_class.domain.entities.subject_class import SubjectClass
from shared.enums.session_status import SessionStatus
from shared.exceptions import ResourceNotFoundException
from shared.pagination import PaginationParams
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_attendance_session_repository import FakeAttendanceSessionRepository
from tests.unit.fakes.fake_subject_class_repository import FakeSubjectClassRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestListAttendanceSessionsUseCase:

    async def test_list_attendance_sessions_paginated_success(self):
        """Deve listar sessões de chamada paginadas com sucesso."""
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()

        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        sc = SubjectClass(tenant_id=tenant.id, name="Matemática I", discipline_name="Matemática")
        await subject_class_repo.save(sc)

        now = datetime.now(timezone.utc)
        s1 = AttendanceSession(subject_class_id=sc.id, day_code="1111", expires_at=now + timedelta(minutes=30), opened_at=now - timedelta(hours=2))
        s2 = AttendanceSession(subject_class_id=sc.id, day_code="2222", expires_at=now + timedelta(minutes=30), opened_at=now - timedelta(hours=1))
        await session_repo.save(s1)
        await session_repo.save(s2)

        use_case = ListAttendanceSessionsUseCase(
            session_repo=session_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
        )

        page = await use_case.execute(
            ListAttendanceSessionsInput(
                tenant_id=tenant.id,
                subject_class_id=sc.id,
                pagination=PaginationParams(page=1, page_size=10),
            )
        )

        assert page.total == 2
        assert len(page.items) == 2
        assert page.items[0].day_code == "2222"  # Descending order by opened_at

    async def test_list_attendance_sessions_filters_by_period_and_status(self):
        """Deve filtrar sessões por período (opened_after/before) e status."""
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()

        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        sc = SubjectClass(tenant_id=tenant.id, name="Física I", discipline_name="Física")
        await subject_class_repo.save(sc)

        base_time = datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc)
        s_old = AttendanceSession(
            subject_class_id=sc.id,
            day_code="OLD1",
            expires_at=base_time + timedelta(minutes=30),
            opened_at=base_time - timedelta(days=30),
            status=SessionStatus.CLOSED,
        )
        s_recent = AttendanceSession(
            subject_class_id=sc.id,
            day_code="REC1",
            expires_at=base_time + timedelta(minutes=30),
            opened_at=base_time,
            status=SessionStatus.OPEN,
        )
        await session_repo.save(s_old)
        await session_repo.save(s_recent)

        use_case = ListAttendanceSessionsUseCase(
            session_repo=session_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
        )

        # Filter by status
        page_open = await use_case.execute(
            ListAttendanceSessionsInput(
                tenant_id=tenant.id,
                subject_class_id=sc.id,
                status=SessionStatus.OPEN,
            )
        )
        assert page_open.total == 1
        assert page_open.items[0].day_code == "REC1"

        # Filter by opened_after
        page_period = await use_case.execute(
            ListAttendanceSessionsInput(
                tenant_id=tenant.id,
                subject_class_id=sc.id,
                opened_after=base_time - timedelta(days=1),
            )
        )
        assert page_period.total == 1
        assert page_period.items[0].day_code == "REC1"

    async def test_list_attendance_sessions_not_found_errors(self):
        """Deve lançar ResourceNotFoundException quando tenant ou turma não existem."""
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        use_case = ListAttendanceSessionsUseCase(
            session_repo=session_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
        )

        # Tenant not found
        with pytest.raises(ResourceNotFoundException, match="Instituição/tenant não encontrada."):
            await use_case.execute(
                ListAttendanceSessionsInput(tenant_id=uuid4(), subject_class_id=uuid4())
            )

        # Class not found
        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)
        with pytest.raises(ResourceNotFoundException, match="Turma não encontrada."):
            await use_case.execute(
                ListAttendanceSessionsInput(tenant_id=tenant.id, subject_class_id=uuid4())
            )
