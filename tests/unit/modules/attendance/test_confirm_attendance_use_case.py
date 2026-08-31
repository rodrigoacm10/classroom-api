from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.attendance.application.use_cases.confirm_attendance import ConfirmAttendanceInput, ConfirmAttendanceUseCase
from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.room.domain.entities.room import Room
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ForbiddenException, ResourceAlreadyExistsException
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_attendance_record_repository import FakeAttendanceRecordRepository
from tests.unit.fakes.fake_attendance_session_repository import FakeAttendanceSessionRepository
from tests.unit.fakes.fake_enrollment_repository import FakeEnrollmentRepository
from tests.unit.fakes.fake_room_repository import FakeRoomRepository
from tests.unit.fakes.fake_subject_class_repository import FakeSubjectClassRepository
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestConfirmAttendanceUseCase:

    async def _setup_fixtures(self):
        session_repo = FakeAttendanceSessionRepository()
        record_repo = FakeAttendanceRecordRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        enrollment_repo = FakeEnrollmentRepository()
        room_repo = FakeRoomRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        user_id = uuid4()
        student_member = TenantMember(tenant_id=tenant.id, user_id=user_id, role=UserRole.ALUNO)
        await member_repo.save(student_member)

        room = Room(tenant_id=tenant.id, name="Sala 101", latitude=-8.047600, longitude=-34.877000, tolerance_radius_meters=50)
        await room_repo.save(room)
        record_repo.seed_room_location(room.id, -8.047600, -34.877000)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma POO",
            discipline_name="POO",
            professor_id=uuid4(),
            room_id=room.id,
        )
        await subject_class_repo.save(subject_class)

        enrollment = Enrollment(
            subject_class_id=subject_class.id,
            tenant_member_id=student_member.id,
            status=EnrollmentStatus.ACTIVE,
        )
        await enrollment_repo.save(enrollment)

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        session = AttendanceSession(
            subject_class_id=subject_class.id,
            room_id=room.id,
            day_code="X3KP7Q",
            expires_at=expires_at,
            status=SessionStatus.OPEN,
        )
        await session_repo.save(session)

        use_case = ConfirmAttendanceUseCase(
            session_repo=session_repo,
            record_repo=record_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
            enrollment_repo=enrollment_repo,
            room_repo=room_repo,
        )

        return (
            use_case,
            tenant,
            subject_class,
            session,
            user_id,
            student_member,
            room,
            record_repo,
            session_repo,
        )

    async def test_confirm_attendance_inside_radius_regular(self):
        """Confirmação dentro do raio geográfico deve ser gravada como REGULAR sem flags."""
        (
            use_case,
            tenant,
            subject_class,
            session,
            user_id,
            student_member,
            room, _, _,
        ) = await self._setup_fixtures()

        record = await use_case.execute(
            ConfirmAttendanceInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                session_id=session.id,
                user_id=user_id,
                day_code="X3KP7Q",
                latitude=-8.047610,  # ~15m da sala
                longitude=-34.877010,
                user_agent="okhttp/4.9.0",
            )
        )

        assert record.within_radius is True
        assert record.record_status == RecordStatus.REGULAR
        assert record.irregularity_flags == []

    async def test_confirm_attendance_outside_radius_flag(self):
        """Confirmação fora do raio grava como IRREGULAR com a flag outside_radius."""
        (
            use_case,
            tenant,
            subject_class,
            session,
            user_id,
            student_member,
            room, _, _,
        ) = await self._setup_fixtures()

        record = await use_case.execute(
            ConfirmAttendanceInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                session_id=session.id,
                user_id=user_id,
                day_code="X3KP7Q",
                latitude=-8.056000,  # ~1km distante da sala
                longitude=-34.877000,
                user_agent="okhttp/4.9.0",
            )
        )

        assert record.within_radius is False
        assert record.record_status == RecordStatus.IRREGULAR
        assert "outside_radius" in record.irregularity_flags

    async def test_confirm_attendance_low_gps_accuracy_flag(self):
        """Precisão de GPS maior que a tolerância da sala spara flag low_gps_accuracy."""
        (
            use_case,
            tenant,
            subject_class,
            session,
            user_id,
            student_member,
            room, _, _,
        ) = await self._setup_fixtures()

        record = await use_case.execute(
            ConfirmAttendanceInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                session_id=session.id,
                user_id=user_id,
                day_code="X3KP7Q",
                latitude=-8.047610,
                longitude=-34.877010,
                gps_accuracy_meters=100.0,  # > tolerância (50m)
                user_agent="okhttp/4.9.0",
            )
        )

        assert record.record_status == RecordStatus.IRREGULAR
        assert "low_gps_accuracy" in record.irregularity_flags

    async def test_confirm_attendance_near_expiry_flag(self):
        """Confirmação a menos de 30 segundos do término dispara flag confirmed_near_expiry."""
        (
            use_case,
            tenant,
            subject_class,
            session,
            user_id,
            student_member,
            room, _,
            session_repo,
        ) = await self._setup_fixtures()

        session.expires_at = datetime.now(timezone.utc) + timedelta(seconds=10)
        await session_repo.save(session)

        record = await use_case.execute(
            ConfirmAttendanceInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                session_id=session.id,
                user_id=user_id,
                day_code="X3KP7Q",
                latitude=-8.047610,
                longitude=-34.877010,
                user_agent="okhttp/4.9.0",
            )
        )

        assert record.record_status == RecordStatus.IRREGULAR
        assert "confirmed_near_expiry" in record.irregularity_flags

    async def test_confirm_attendance_non_mobile_client_flag(self):
        """User agent de navegador de desktop dispara flag non_mobile_client."""
        (
            use_case,
            tenant,
            subject_class,
            session,
            user_id,
            student_member,
            room, _, _,
        ) = await self._setup_fixtures()

        record = await use_case.execute(
            ConfirmAttendanceInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                session_id=session.id,
                user_id=user_id,
                day_code="X3KP7Q",
                latitude=-8.047610,
                longitude=-34.877010,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            )
        )

        assert record.record_status == RecordStatus.IRREGULAR
        assert "non_mobile_client" in record.irregularity_flags

    async def test_confirm_attendance_shared_device_flag(self):
        """Mesmo device_id usado por outro aluno dispara flag shared_device."""
        (
            use_case,
            tenant,
            subject_class,
            session,
            user_id,
            student_member,
            room,
            record_repo, _,
        ) = await self._setup_fixtures()

        device_id = "device-uuid-1234"
        # Seed record de outro aluno na mesma sessão com o mesmo device_id
        await record_repo.create_record(
            session_id=session.id,
            tenant_member_id=uuid4(),
            latitude=-8.0476,
            longitude=-34.877,
            room_id=room.id,
            tolerance_radius_meters=50,
            device_id=device_id,
        )

        record = await use_case.execute(
            ConfirmAttendanceInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                session_id=session.id,
                user_id=user_id,
                day_code="X3KP7Q",
                latitude=-8.047610,
                longitude=-34.877010,
                device_id=device_id,
                user_agent="okhttp/4.9.0",
            )
        )

        assert record.record_status == RecordStatus.IRREGULAR
        assert "shared_device" in record.irregularity_flags

    async def test_confirm_attendance_raises_when_session_closed(self):
        """Deve lançar ResourceAlreadyExistsException se a chamada estiver fechada."""
        (
            use_case,
            tenant,
            subject_class,
            session,
            user_id, _, _, _,
            session_repo,
        ) = await self._setup_fixtures()

        session.status = SessionStatus.CLOSED
        await session_repo.save(session)

        with pytest.raises(ResourceAlreadyExistsException, match="A chamada está encerrada"):
            await use_case.execute(
                ConfirmAttendanceInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    session_id=session.id,
                    user_id=user_id,
                    day_code="X3KP7Q",
                    latitude=-8.047610,
                    longitude=-34.877010,
                )
            )

    async def test_confirm_attendance_raises_when_session_cancelled(self):
        """Deve lançar ResourceAlreadyExistsException se a chamada estiver cancelada."""
        (
            use_case,
            tenant,
            subject_class,
            session,
            user_id, _, _, _,
            session_repo,
        ) = await self._setup_fixtures()

        session.status = SessionStatus.CANCELLED
        await session_repo.save(session)

        with pytest.raises(ResourceAlreadyExistsException, match="A chamada foi cancelada"):
            await use_case.execute(
                ConfirmAttendanceInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    session_id=session.id,
                    user_id=user_id,
                    day_code="X3KP7Q",
                    latitude=-8.047610,
                    longitude=-34.877010,
                )
            )

    async def test_confirm_attendance_raises_when_session_expired(self):
        """Deve lançar ResourceAlreadyExistsException se a chamada estiver expirada."""
        (
            use_case,
            tenant,
            subject_class,
            session,
            user_id, _, _, _,
            session_repo,
        ) = await self._setup_fixtures()

        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        await session_repo.save(session)

        with pytest.raises(ResourceAlreadyExistsException, match="A chamada está expirada"):
            await use_case.execute(
                ConfirmAttendanceInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    session_id=session.id,
                    user_id=user_id,
                    day_code="X3KP7Q",
                    latitude=-8.047610,
                    longitude=-34.877010,
                )
            )

    async def test_confirm_attendance_raises_when_invalid_day_code(self):
        """Deve lançar BusinessRuleException se o day_code for incorreto."""
        (
            use_case,
            tenant,
            subject_class,
            session,
            user_id, _, _, _, _,
        ) = await self._setup_fixtures()

        with pytest.raises(BusinessRuleException, match="Código da chamada inválido"):
            await use_case.execute(
                ConfirmAttendanceInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    session_id=session.id,
                    user_id=user_id,
                    day_code="WRONG1",
                    latitude=-8.047610,
                    longitude=-34.877010,
                )
            )

    async def test_confirm_attendance_raises_when_no_active_enrollment(self):
        """Deve lançar ForbiddenException se aluno não possuir matrícula ativa na turma."""
        (
            use_case,
            tenant,
            subject_class,
            session, _, _, _, _, _,
        ) = await self._setup_fixtures()

        non_enrolled_user = uuid4()

        with pytest.raises(ForbiddenException):
            await use_case.execute(
                ConfirmAttendanceInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    session_id=session.id,
                    user_id=non_enrolled_user,
                    day_code="X3KP7Q",
                    latitude=-8.047610,
                    longitude=-34.877010,
                )
            )

    async def test_confirm_attendance_raises_when_already_confirmed(self):
        """Deve lançar ResourceAlreadyExistsException se aluno tentar confirmar presença duas vezes na mesma chamada."""
        (
            use_case,
            tenant,
            subject_class,
            session,
            user_id, _, _, _, _,
        ) = await self._setup_fixtures()

        await use_case.execute(
            ConfirmAttendanceInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                session_id=session.id,
                user_id=user_id,
                day_code="X3KP7Q",
                latitude=-8.047610,
                longitude=-34.877010,
                user_agent="okhttp/4.9.0",
            )
        )

        with pytest.raises(ResourceAlreadyExistsException, match="Presença já confirmada"):
            await use_case.execute(
                ConfirmAttendanceInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    session_id=session.id,
                    user_id=user_id,
                    day_code="X3KP7Q",
                    latitude=-8.047610,
                    longitude=-34.877010,
                    user_agent="okhttp/4.9.0",
                )
            )
