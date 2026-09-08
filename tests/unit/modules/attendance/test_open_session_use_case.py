from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.attendance.application.use_cases.open_session import OpenAttendanceSessionInput, OpenAttendanceSessionUseCase
from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.attendance.domain.events.attendance_events import AttendanceSessionOpenedEvent
from modules.room.domain.entities.room import Room
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.events.event_dispatcher import EventDispatcher
from shared.exceptions import ForbiddenException, ResourceAlreadyExistsException, ResourceNotFoundException
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_attendance_session_repository import FakeAttendanceSessionRepository
from tests.unit.fakes.fake_room_repository import FakeRoomRepository
from tests.unit.fakes.fake_subject_class_repository import FakeSubjectClassRepository
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


def make_use_case(session_repo, subject_class_repo, tenant_repo, member_repo, room_repo, event_dispatcher=None):
    """Helper para instanciar o use case com um dispatcher (real ou no-op)."""
    return OpenAttendanceSessionUseCase(
        session_repo=session_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        member_repo=member_repo,
        room_repo=room_repo,
        event_dispatcher=event_dispatcher or EventDispatcher(),
    )


@pytest.mark.asyncio
class TestOpenAttendanceSessionUseCase:

    async def test_open_session_success(self):
        """Deve abrir uma nova sessão de chamada com day_code de 6 caracteres e status OPEN."""
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        room_repo = FakeRoomRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        user_id = uuid4()
        professor_member = TenantMember(tenant_id=tenant.id, user_id=user_id, role=UserRole.PROFESSOR)
        await member_repo.save(professor_member)

        room = Room(tenant_id=tenant.id, name="Sala 101", latitude=-8.0, longitude=-34.0)
        await room_repo.save(room)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma POO",
            discipline_name="POO",
            professor_id=professor_member.id,
            room_id=room.id,
        )
        await subject_class_repo.save(subject_class)

        use_case = make_use_case(session_repo, subject_class_repo, tenant_repo, member_repo, room_repo)

        session = await use_case.execute(
            OpenAttendanceSessionInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                user_id=user_id,
                user_role=UserRole.PROFESSOR,
                duration_minutes=20,
            )
        )

        assert session.subject_class_id == subject_class.id
        assert session.room_id == room.id
        assert len(session.day_code) == 6
        assert session.status == SessionStatus.OPEN
        assert session.is_open is True
        assert session.is_expired is False

    async def test_open_session_publishes_opened_event(self):
        """Deve publicar AttendanceSessionOpenedEvent com os dados corretos após salvar sessão."""
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        room_repo = FakeRoomRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        user_id = uuid4()
        professor_member = TenantMember(tenant_id=tenant.id, user_id=user_id, role=UserRole.PROFESSOR)
        await member_repo.save(professor_member)

        room = Room(tenant_id=tenant.id, name="Sala 101", latitude=-8.0, longitude=-34.0)
        await room_repo.save(room)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma POO",
            discipline_name="POO",
            professor_id=professor_member.id,
            room_id=room.id,
        )
        await subject_class_repo.save(subject_class)

        # Spy: coleta os eventos publicados
        captured_events: list = []

        async def spy_handler(event):
            captured_events.append(event)

        dispatcher = EventDispatcher()
        dispatcher.register(AttendanceSessionOpenedEvent, spy_handler)

        use_case = make_use_case(session_repo, subject_class_repo, tenant_repo, member_repo, room_repo, dispatcher)

        session = await use_case.execute(
            OpenAttendanceSessionInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                user_id=user_id,
                user_role=UserRole.PROFESSOR,
                duration_minutes=15,
            )
        )

        assert len(captured_events) == 1
        event = captured_events[0]
        assert isinstance(event, AttendanceSessionOpenedEvent)
        assert event.session_id == session.id
        assert event.subject_class_id == subject_class.id
        assert event.day_code == session.day_code
        assert event.duration_minutes == 15
        assert event.subject_class_name == subject_class.name

    async def test_open_session_raises_409_when_already_open(self):
        """Deve lançar BusinessRuleException (409) se já existir chamada aberta para a turma."""
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        room_repo = FakeRoomRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        user_id = uuid4()
        professor_member = TenantMember(tenant_id=tenant.id, user_id=user_id, role=UserRole.PROFESSOR)
        await member_repo.save(professor_member)

        room = Room(tenant_id=tenant.id, name="Sala 101", latitude=-8.0, longitude=-34.0)
        await room_repo.save(room)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma POO",
            discipline_name="POO",
            professor_id=professor_member.id,
            room_id=room.id,
        )
        await subject_class_repo.save(subject_class)

        existing_session = AttendanceSession(
            subject_class_id=subject_class.id,
            room_id=room.id,
            day_code="ABC123",
            expires_at=datetime.now(timezone.utc),
        )
        # Forçar expires_at no futuro
        existing_session.expires_at = datetime.now(timezone.utc).replace(year=2030)
        await session_repo.save(existing_session)

        use_case = make_use_case(session_repo, subject_class_repo, tenant_repo, member_repo, room_repo)

        with pytest.raises(ResourceAlreadyExistsException, match="Já existe uma chamada aberta"):
            await use_case.execute(
                OpenAttendanceSessionInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    user_id=user_id,
                    user_role=UserRole.PROFESSOR,
                )
            )

    async def test_open_session_raises_403_when_not_professor_nor_admin(self):
        """Deve lançar ForbiddenException se usuário não for o professor da turma nem admin."""
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        room_repo = FakeRoomRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        other_user_id = uuid4()
        other_member = TenantMember(tenant_id=tenant.id, user_id=other_user_id, role=UserRole.ALUNO)
        await member_repo.save(other_member)

        room = Room(tenant_id=tenant.id, name="Sala 101", latitude=-8.0, longitude=-34.0)
        await room_repo.save(room)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma POO",
            discipline_name="POO",
            professor_id=uuid4(),
            room_id=room.id,
        )
        await subject_class_repo.save(subject_class)

        use_case = make_use_case(session_repo, subject_class_repo, tenant_repo, member_repo, room_repo)

        with pytest.raises(ForbiddenException):
            await use_case.execute(
                OpenAttendanceSessionInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    user_id=other_user_id,
                    user_role=UserRole.ALUNO,
                )
            )

    async def test_open_session_raises_403_when_different_professor(self):
        """Deve lançar ForbiddenException se outro professor tentar abrir chamada em turma que não leciona."""
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        room_repo = FakeRoomRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        diff_prof_user_id = uuid4()
        diff_prof_member = TenantMember(tenant_id=tenant.id, user_id=diff_prof_user_id, role=UserRole.PROFESSOR)
        await member_repo.save(diff_prof_member)

        room = Room(tenant_id=tenant.id, name="Sala 101", latitude=-8.0, longitude=-34.0)
        await room_repo.save(room)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma POO",
            discipline_name="POO",
            professor_id=uuid4(),  # Outro professor vinculado
            room_id=room.id,
        )
        await subject_class_repo.save(subject_class)

        use_case = make_use_case(session_repo, subject_class_repo, tenant_repo, member_repo, room_repo)

        with pytest.raises(ForbiddenException, match="Apenas o professor da turma ou um administrador"):
            await use_case.execute(
                OpenAttendanceSessionInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    user_id=diff_prof_user_id,
                    user_role=UserRole.PROFESSOR,
                )
            )

    async def test_open_session_raises_404_when_room_not_found(self):
        """Deve lançar ResourceNotFoundException se a sala especificada não for encontrada."""
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        room_repo = FakeRoomRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        user_id = uuid4()
        professor_member = TenantMember(tenant_id=tenant.id, user_id=user_id, role=UserRole.PROFESSOR)
        await member_repo.save(professor_member)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma POO",
            discipline_name="POO",
            professor_id=professor_member.id,
            room_id=None,
        )
        await subject_class_repo.save(subject_class)

        use_case = make_use_case(session_repo, subject_class_repo, tenant_repo, member_repo, room_repo)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                OpenAttendanceSessionInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    user_id=user_id,
                    user_role=UserRole.PROFESSOR,
                    room_id=uuid4(),
                )
            )
