import uuid
from datetime import datetime, timedelta, timezone

import pytest

from modules.attendance.application.use_cases.list_active_sessions import (
    ListActiveAttendanceSessionsUseCase,
    ListActiveSessionsInput,
)
from modules.attendance.domain.entities.attendance_session import AttendanceSession
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_attendance_session_repository import FakeAttendanceSessionRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestListActiveAttendanceSessionsUseCase:
    async def test_professor_sees_only_own_active_sessions(self) -> None:
        """Deve retornar apenas as chamadas abertas e não expiradas vinculadas ao professor solicitante."""
        tenant_repo = FakeTenantRepository()
        session_repo = FakeAttendanceSessionRepository()
        use_case = ListActiveAttendanceSessionsUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
        )

        tenant = TenantFactory.make(name="Escola A")
        tenant_repo.seed(tenant)

        prof1_user_id = uuid.uuid4()
        prof2_user_id = uuid.uuid4()

        now = datetime.now(timezone.utc)
        # Sessão do professor 1 (aberta)
        s1 = AttendanceSession(
            subject_class_id=uuid.uuid4(),
            day_code="1234",
            opened_at=now,
            expires_at=now + timedelta(minutes=30),
            status=SessionStatus.OPEN,
        )
        setattr(s1, "_tenant_id", tenant.id)
        setattr(s1, "_professor_user_id", prof1_user_id)
        await session_repo.save(s1)

        # Sessão do professor 2 (aberta)
        s2 = AttendanceSession(
            subject_class_id=uuid.uuid4(),
            day_code="5678",
            opened_at=now,
            expires_at=now + timedelta(minutes=30),
            status=SessionStatus.OPEN,
        )
        setattr(s2, "_tenant_id", tenant.id)
        setattr(s2, "_professor_user_id", prof2_user_id)
        await session_repo.save(s2)

        # Sessão do professor 1 expirada (não deve vir)
        s3 = AttendanceSession(
            subject_class_id=uuid.uuid4(),
            day_code="9999",
            opened_at=now - timedelta(minutes=60),
            expires_at=now - timedelta(minutes=10),
            status=SessionStatus.OPEN,
        )
        setattr(s3, "_tenant_id", tenant.id)
        setattr(s3, "_professor_user_id", prof1_user_id)
        await session_repo.save(s3)

        # Professor 1 consulta
        results = await use_case.execute(
            ListActiveSessionsInput(
                tenant_id=tenant.id,
                user_id=prof1_user_id,
                user_role=UserRole.PROFESSOR,
            )
        )

        assert len(results) == 1
        assert results[0].id == s1.id
        assert results[0].day_code == "1234"

    async def test_admin_sees_all_tenant_active_sessions(self) -> None:
        """Deve retornar todas as chamadas abertas da instituição para usuários com papel ADMIN."""
        tenant_repo = FakeTenantRepository()
        session_repo = FakeAttendanceSessionRepository()
        use_case = ListActiveAttendanceSessionsUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
        )

        tenant = TenantFactory.make(name="Escola A")
        tenant_repo.seed(tenant)

        admin_user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        s1 = AttendanceSession(
            subject_class_id=uuid.uuid4(),
            day_code="1111",
            opened_at=now,
            expires_at=now + timedelta(minutes=15),
            status=SessionStatus.OPEN,
        )
        setattr(s1, "_tenant_id", tenant.id)
        setattr(s1, "_professor_user_id", uuid.uuid4())
        await session_repo.save(s1)

        s2 = AttendanceSession(
            subject_class_id=uuid.uuid4(),
            day_code="2222",
            opened_at=now,
            expires_at=now + timedelta(minutes=20),
            status=SessionStatus.OPEN,
        )
        setattr(s2, "_tenant_id", tenant.id)
        setattr(s2, "_professor_user_id", uuid.uuid4())
        await session_repo.save(s2)

        results = await use_case.execute(
            ListActiveSessionsInput(
                tenant_id=tenant.id,
                user_id=admin_user_id,
                user_role=UserRole.ADMIN,
            )
        )

        assert len(results) == 2

    async def test_student_role_raises_forbidden_exception(self) -> None:
        """Deve lançar ForbiddenException quando um usuário com papel ALUNO tentar consultar chamadas ativas."""
        tenant_repo = FakeTenantRepository()
        session_repo = FakeAttendanceSessionRepository()
        use_case = ListActiveAttendanceSessionsUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
        )

        tenant = TenantFactory.make(name="Escola A")
        tenant_repo.seed(tenant)

        with pytest.raises(ForbiddenException):
            await use_case.execute(
                ListActiveSessionsInput(
                    tenant_id=tenant.id,
                    user_id=uuid.uuid4(),
                    user_role=UserRole.ALUNO,
                )
            )

    async def test_tenant_not_found_raises_resource_not_found(self) -> None:
        """Deve lançar ResourceNotFoundException quando a instituição/tenant não for encontrada."""
        tenant_repo = FakeTenantRepository()
        session_repo = FakeAttendanceSessionRepository()
        use_case = ListActiveAttendanceSessionsUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                ListActiveSessionsInput(
                    tenant_id=uuid.uuid4(),
                    user_id=uuid.uuid4(),
                    user_role=UserRole.ADMIN,
                )
            )

    async def test_none_role_raises_forbidden_exception(self) -> None:
        """Deve lançar ForbiddenException quando o papel (role) do usuário for None."""
        tenant_repo = FakeTenantRepository()
        session_repo = FakeAttendanceSessionRepository()
        use_case = ListActiveAttendanceSessionsUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
        )

        tenant = TenantFactory.make(name="Escola A")
        tenant_repo.seed(tenant)

        with pytest.raises(ForbiddenException):
            await use_case.execute(
                ListActiveSessionsInput(
                    tenant_id=tenant.id,
                    user_id=uuid.uuid4(),
                    user_role=None,
                )
            )
