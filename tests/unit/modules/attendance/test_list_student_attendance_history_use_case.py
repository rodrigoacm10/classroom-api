import uuid
from datetime import datetime, timezone

import pytest

from modules.attendance.application.use_cases.list_student_attendance_history import (
    ListStudentAttendanceHistoryInput,
    ListStudentAttendanceHistoryUseCase,
)
from modules.attendance.domain.entities.student_attendance_history_item import (
    StudentAttendanceHistoryItem,
)
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException
from shared.pagination import PaginationParams
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_attendance_session_repository import FakeAttendanceSessionRepository
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestListStudentAttendanceHistoryUseCase:
    async def test_student_sees_attendance_history(self) -> None:
        """Aluno matriculado consulta seu histórico de chamadas com sucesso."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        session_repo = FakeAttendanceSessionRepository()

        use_case = ListStudentAttendanceHistoryUseCase(
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
        fake_item = StudentAttendanceHistoryItem(
            session_id=uuid.uuid4(),
            subject_class_id=uuid.uuid4(),
            subject_class_name="T01",
            discipline_name="Algoritmos e Estruturas de Dados",
            opened_at=now,
            session_status=SessionStatus.CLOSED,
            record_status=RecordStatus.REGULAR,
            confirmed_at=now,
            room_name="Lab 204",
        )
        session_repo._student_history_items = [fake_item]

        page = await use_case.execute(
            ListStudentAttendanceHistoryInput(
                tenant_id=tenant.id,
                user_id=student_user_id,
                user_role=UserRole.ALUNO,
                pagination=PaginationParams(page=1, page_size=20),
            )
        )

        assert page.total == 1
        assert len(page.items) == 1
        assert page.items[0].session_id == fake_item.session_id
        assert page.items[0].record_status == RecordStatus.REGULAR
        assert page.items[0].session_status == SessionStatus.CLOSED
        assert page.items[0].room_name == "Lab 204"

    async def test_student_history_filters_by_subject_class_and_status(self) -> None:
        """Filtro por turma e status da sessão funcionam corretamente."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        session_repo = FakeAttendanceSessionRepository()

        use_case = ListStudentAttendanceHistoryUseCase(
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
        class1_id = uuid.uuid4()
        class2_id = uuid.uuid4()

        item1 = StudentAttendanceHistoryItem(
            session_id=uuid.uuid4(),
            subject_class_id=class1_id,
            subject_class_name="T01",
            discipline_name="Algoritmos",
            opened_at=now,
            session_status=SessionStatus.CLOSED,
            record_status=RecordStatus.REGULAR,
        )
        item2 = StudentAttendanceHistoryItem(
            session_id=uuid.uuid4(),
            subject_class_id=class2_id,
            subject_class_name="T02",
            discipline_name="Banco de Dados",
            opened_at=now,
            session_status=SessionStatus.OPEN,
            record_status=None,
        )
        session_repo._student_history_items = [item1, item2]

        # Filtra por turma 1
        res1 = await use_case.execute(
            ListStudentAttendanceHistoryInput(
                tenant_id=tenant.id,
                user_id=student_user_id,
                user_role=UserRole.ALUNO,
                pagination=PaginationParams(page=1, page_size=20),
                subject_class_id=class1_id,
            )
        )
        assert res1.total == 1
        assert res1.items[0].subject_class_id == class1_id

        # Filtra por status OPEN
        res2 = await use_case.execute(
            ListStudentAttendanceHistoryInput(
                tenant_id=tenant.id,
                user_id=student_user_id,
                user_role=UserRole.ALUNO,
                pagination=PaginationParams(page=1, page_size=20),
                status=SessionStatus.OPEN,
            )
        )
        assert res2.total == 1
        assert res2.items[0].session_status == SessionStatus.OPEN

    async def test_student_history_pagination(self) -> None:
        """Paginação divide corretamente os resultados."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        session_repo = FakeAttendanceSessionRepository()

        use_case = ListStudentAttendanceHistoryUseCase(
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
        items = [
            StudentAttendanceHistoryItem(
                session_id=uuid.uuid4(),
                subject_class_id=uuid.uuid4(),
                subject_class_name=f"T0{i}",
                discipline_name=f"Discipline {i}",
                opened_at=now,
                session_status=SessionStatus.CLOSED,
            )
            for i in range(5)
        ]
        session_repo._student_history_items = items

        page1 = await use_case.execute(
            ListStudentAttendanceHistoryInput(
                tenant_id=tenant.id,
                user_id=student_user_id,
                user_role=UserRole.ALUNO,
                pagination=PaginationParams(page=1, page_size=2),
            )
        )
        assert page1.total == 5
        assert len(page1.items) == 2
        assert page1.page == 1
        assert page1.page_size == 2
        assert page1.pages == 3

    async def test_non_member_raises_forbidden(self) -> None:
        """Usuário que não é membro da instituição recebe ForbiddenException."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        session_repo = FakeAttendanceSessionRepository()

        use_case = ListStudentAttendanceHistoryUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        tenant = TenantFactory.make(name="Faculdade Tech")
        tenant_repo.seed(tenant)

        with pytest.raises(ForbiddenException, match="Usuário não é membro"):
            await use_case.execute(
                ListStudentAttendanceHistoryInput(
                    tenant_id=tenant.id,
                    user_id=uuid.uuid4(),
                    user_role=UserRole.ALUNO,
                    pagination=PaginationParams(page=1, page_size=20),
                )
            )

    async def test_non_student_role_raises_forbidden(self) -> None:
        """Professor tentando consultar histórico de chamadas do aluno recebe ForbiddenException."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        session_repo = FakeAttendanceSessionRepository()

        use_case = ListStudentAttendanceHistoryUseCase(
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
            ForbiddenException, match="Apenas alunos podem consultar seu histórico de chamadas"
        ):
            await use_case.execute(
                ListStudentAttendanceHistoryInput(
                    tenant_id=tenant.id,
                    user_id=prof_user_id,
                    user_role=UserRole.PROFESSOR,
                    pagination=PaginationParams(page=1, page_size=20),
                )
            )

    async def test_tenant_not_found_raises_exception(self) -> None:
        """Tenant inexistente levanta ResourceNotFoundException."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        session_repo = FakeAttendanceSessionRepository()

        use_case = ListStudentAttendanceHistoryUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        with pytest.raises(ResourceNotFoundException, match="Instituição/tenant não encontrada"):
            await use_case.execute(
                ListStudentAttendanceHistoryInput(
                    tenant_id=uuid.uuid4(),
                    user_id=uuid.uuid4(),
                    user_role=UserRole.ALUNO,
                    pagination=PaginationParams(page=1, page_size=20),
                )
            )

    async def test_admin_can_view_student_history(self) -> None:
        """Admin pode consultar histórico de chamadas de um aluno específico."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        session_repo = FakeAttendanceSessionRepository()

        use_case = ListStudentAttendanceHistoryUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        tenant = TenantFactory.make(name="Faculdade Tech")
        tenant_repo.seed(tenant)

        admin_member = TenantMember(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            role=UserRole.ADMIN,
        )
        member_repo.seed(admin_member)

        student_member = TenantMember(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            role=UserRole.ALUNO,
        )
        member_repo.seed(student_member)

        now = datetime.now(timezone.utc)
        fake_item = StudentAttendanceHistoryItem(
            session_id=uuid.uuid4(),
            subject_class_id=uuid.uuid4(),
            subject_class_name="T01",
            discipline_name="Algoritmos",
            opened_at=now,
            session_status=SessionStatus.CLOSED,
            record_status=RecordStatus.REGULAR,
            confirmed_at=now,
            room_name="Lab 101",
        )
        session_repo._student_history_items = [fake_item]

        result = await use_case.execute(
            ListStudentAttendanceHistoryInput(
                tenant_id=tenant.id,
                user_id=admin_member.user_id,
                user_role=UserRole.ADMIN,
                target_tenant_member_id=student_member.id,
                pagination=PaginationParams(page=1, page_size=20),
            )
        )

        assert len(result.items) == 1
        assert result.items[0].discipline_name == "Algoritmos"
