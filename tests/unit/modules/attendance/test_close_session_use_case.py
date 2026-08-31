from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.attendance.application.use_cases.close_session import CloseAttendanceSessionInput, CloseAttendanceSessionUseCase
from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ForbiddenException, ResourceAlreadyExistsException, ResourceNotFoundException
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_attendance_session_repository import FakeAttendanceSessionRepository
from tests.unit.fakes.fake_subject_class_repository import FakeSubjectClassRepository
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestCloseAttendanceSessionUseCase:

    async def test_close_session_success(self):
        """Deve encerrar uma chamada aberta setando status=CLOSED e preenchendo closed_at."""
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        user_id = uuid4()
        professor_member = TenantMember(tenant_id=tenant.id, user_id=user_id, role=UserRole.PROFESSOR)
        await member_repo.save(professor_member)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma BD",
            discipline_name="BD",
            professor_id=professor_member.id,
        )
        await subject_class_repo.save(subject_class)

        session = AttendanceSession(
            subject_class_id=subject_class.id,
            day_code="X3KP7Q",
            expires_at=datetime.now(timezone.utc),
            status=SessionStatus.OPEN,
        )
        await session_repo.save(session)

        use_case = CloseAttendanceSessionUseCase(
            session_repo=session_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        closed = await use_case.execute(
            CloseAttendanceSessionInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                session_id=session.id,
                user_id=user_id,
                user_role=UserRole.PROFESSOR,
            )
        )

        assert closed.status == SessionStatus.CLOSED
        assert closed.closed_at is not None

    async def test_close_session_raises_409_when_already_closed(self):
        """Deve lançar BusinessRuleException (409) ao tentar fechar uma chamada já encerrada."""
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        user_id = uuid4()
        professor_member = TenantMember(tenant_id=tenant.id, user_id=user_id, role=UserRole.PROFESSOR)
        await member_repo.save(professor_member)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma BD",
            discipline_name="BD",
            professor_id=professor_member.id,
        )
        await subject_class_repo.save(subject_class)

        session = AttendanceSession(
            subject_class_id=subject_class.id,
            day_code="X3KP7Q",
            expires_at=datetime.now(timezone.utc),
            status=SessionStatus.CLOSED,
        )
        await session_repo.save(session)

        use_case = CloseAttendanceSessionUseCase(
            session_repo=session_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        with pytest.raises(ResourceAlreadyExistsException, match="A chamada já está encerrada"):
            await use_case.execute(
                CloseAttendanceSessionInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    session_id=session.id,
                    user_id=user_id,
                    user_role=UserRole.PROFESSOR,
                )
            )

    async def test_close_session_raises_403_when_not_authorized(self):
        """Deve lançar ForbiddenException se usuário não for o professor nem admin."""
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        other_user_id = uuid4()
        other_member = TenantMember(tenant_id=tenant.id, user_id=other_user_id, role=UserRole.ALUNO)
        await member_repo.save(other_member)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma BD",
            discipline_name="BD",
            professor_id=uuid4(),
        )
        await subject_class_repo.save(subject_class)

        session = AttendanceSession(
            subject_class_id=subject_class.id,
            day_code="X3KP7Q",
            expires_at=datetime.now(timezone.utc),
            status=SessionStatus.OPEN,
        )
        await session_repo.save(session)

        use_case = CloseAttendanceSessionUseCase(
            session_repo=session_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        with pytest.raises(ForbiddenException):
            await use_case.execute(
                CloseAttendanceSessionInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    session_id=session.id,
                    user_id=other_user_id,
                    user_role=UserRole.ALUNO,
                )
            )
