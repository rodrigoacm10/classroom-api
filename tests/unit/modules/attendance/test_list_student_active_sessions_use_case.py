import uuid
from datetime import datetime, timedelta, timezone

import pytest

from modules.attendance.application.use_cases.list_student_active_sessions import (
    ListStudentActiveSessionsInput,
    ListStudentActiveSessionsUseCase,
)
from modules.attendance.domain.entities.student_active_session import StudentActiveSession
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_attendance_session_repository import FakeAttendanceSessionRepository
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestListStudentActiveSessionsUseCase:
    async def test_student_sees_active_sessions(self) -> None:
        """Aluno matriculado consulta suas chamadas ativas com sucesso."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        session_repo = FakeAttendanceSessionRepository()

        use_case = ListStudentActiveSessionsUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        tenant = TenantFactory.make(name="Faculdade Tech")
        tenant_repo.seed(tenant)

        student_user_id = uuid.uuid4()
        member = TenantMember(
            tenant_id=tenant.id,
            user_id=student_user_id,
            role=UserRole.ALUNO,
        )
        member_repo.seed(member)

        now = datetime.now(timezone.utc)
        fake_session = StudentActiveSession(
            session_id=uuid.uuid4(),
            subject_class_id=uuid.uuid4(),
            subject_class_name="T01",
            discipline_name="Algoritmos e Estruturas de Dados",
            opened_at=now,
            expires_at=now + timedelta(minutes=15),
            already_confirmed=False,
            room_name="Lab 204",
        )
        session_repo._student_active_sessions = [fake_session]

        result = await use_case.execute(
            ListStudentActiveSessionsInput(
                tenant_id=tenant.id,
                user_id=student_user_id,
                user_role=UserRole.ALUNO,
            )
        )

        assert len(result) == 1
        assert result[0].session_id == fake_session.session_id
        assert result[0].already_confirmed is False
        assert result[0].duration_minutes == 15

    async def test_non_member_raises_forbidden(self) -> None:
        """Usuário que não é membro da instituição recebe ForbiddenException."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        session_repo = FakeAttendanceSessionRepository()

        use_case = ListStudentActiveSessionsUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        tenant = TenantFactory.make(name="Faculdade Tech")
        tenant_repo.seed(tenant)

        with pytest.raises(ForbiddenException, match="Usuário não é membro"):
            await use_case.execute(
                ListStudentActiveSessionsInput(
                    tenant_id=tenant.id,
                    user_id=uuid.uuid4(),
                    user_role=UserRole.ALUNO,
                )
            )

    async def test_non_student_role_raises_forbidden(self) -> None:
        """Professor tentando consultar como aluno recebe ForbiddenException."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        session_repo = FakeAttendanceSessionRepository()

        use_case = ListStudentActiveSessionsUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        tenant = TenantFactory.make(name="Faculdade Tech")
        tenant_repo.seed(tenant)

        prof_user_id = uuid.uuid4()
        prof_member = TenantMember(
            tenant_id=tenant.id,
            user_id=prof_user_id,
            role=UserRole.PROFESSOR,
        )
        member_repo.seed(prof_member)

        with pytest.raises(
            ForbiddenException, match="Apenas alunos podem consultar suas chamadas ativas"
        ):
            await use_case.execute(
                ListStudentActiveSessionsInput(
                    tenant_id=tenant.id,
                    user_id=prof_user_id,
                    user_role=UserRole.PROFESSOR,
                )
            )

    async def test_tenant_not_found_raises_exception(self) -> None:
        """Tenant inexistente levanta ResourceNotFoundException."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        session_repo = FakeAttendanceSessionRepository()

        use_case = ListStudentActiveSessionsUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        with pytest.raises(ResourceNotFoundException, match="Instituição/tenant não encontrada"):
            await use_case.execute(
                ListStudentActiveSessionsInput(
                    tenant_id=uuid.uuid4(),
                    user_id=uuid.uuid4(),
                    user_role=UserRole.ALUNO,
                )
            )
