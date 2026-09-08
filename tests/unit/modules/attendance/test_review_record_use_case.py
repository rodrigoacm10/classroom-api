from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.attendance.application.use_cases.review_record import ReviewAttendanceRecordInput, ReviewAttendanceRecordUseCase
from modules.attendance.domain.entities.attendance_record import AttendanceRecord
from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ForbiddenException
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_attendance_record_repository import FakeAttendanceRecordRepository
from tests.unit.fakes.fake_attendance_session_repository import FakeAttendanceSessionRepository
from tests.unit.fakes.fake_subject_class_repository import FakeSubjectClassRepository
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestReviewAttendanceRecordUseCase:

    async def test_review_record_approve_success(self):
        """Professor aprova um registro irregular preenchendo reviewed_by e reviewed_at."""
        record_repo = FakeAttendanceRecordRepository()
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        prof_user_id = uuid4()
        professor_member = TenantMember(tenant_id=tenant.id, user_id=prof_user_id, role=UserRole.PROFESSOR)
        await member_repo.save(professor_member)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma POO",
            discipline_name="POO",
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

        record = AttendanceRecord(
            session_id=session.id,
            tenant_member_id=uuid4(),
            latitude=-8.0,
            longitude=-34.0,
            distance_meters=87.0,
            within_radius=False,
            record_status=RecordStatus.IRREGULAR,
            irregularity_flags=["outside_radius"],
        )
        await record_repo.save(record)

        use_case = ReviewAttendanceRecordUseCase(
            record_repo=record_repo,
            session_repo=session_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        reviewed = await use_case.execute(
            ReviewAttendanceRecordInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                session_id=session.id,
                record_id=record.id,
                user_id=prof_user_id,
                user_role=UserRole.PROFESSOR,
                decision=RecordStatus.APPROVED,
                note="Aluno justificou estar na entrada do prédio.",
            )
        )

        assert reviewed.record_status == RecordStatus.APPROVED
        assert reviewed.reviewed_by == professor_member.id
        assert reviewed.reviewed_at is not None
        assert reviewed.review_note == "Aluno justificou estar na entrada do prédio."

    async def test_review_record_reject_success(self):
        """Professor rejeita um registro irregular."""
        record_repo = FakeAttendanceRecordRepository()
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        prof_user_id = uuid4()
        professor_member = TenantMember(tenant_id=tenant.id, user_id=prof_user_id, role=UserRole.PROFESSOR)
        await member_repo.save(professor_member)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma POO",
            discipline_name="POO",
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

        record = AttendanceRecord(
            session_id=session.id,
            tenant_member_id=uuid4(),
            latitude=-8.0,
            longitude=-34.0,
            distance_meters=350.0,
            within_radius=False,
            record_status=RecordStatus.IRREGULAR,
            irregularity_flags=["outside_radius"],
        )
        await record_repo.save(record)

        use_case = ReviewAttendanceRecordUseCase(
            record_repo=record_repo,
            session_repo=session_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        reviewed = await use_case.execute(
            ReviewAttendanceRecordInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                session_id=session.id,
                record_id=record.id,
                user_id=prof_user_id,
                user_role=UserRole.PROFESSOR,
                decision=RecordStatus.REJECTED,
                note="Distante demais da sala de aula.",
            )
        )

        assert reviewed.record_status == RecordStatus.REJECTED
        assert reviewed.reviewed_by == professor_member.id

    async def test_review_record_raises_409_when_regular(self):
        """Deve lançar BusinessRuleException (409) se tentar revisar um registro regular."""
        record_repo = FakeAttendanceRecordRepository()
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        prof_user_id = uuid4()
        professor_member = TenantMember(tenant_id=tenant.id, user_id=prof_user_id, role=UserRole.PROFESSOR)
        await member_repo.save(professor_member)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma POO",
            discipline_name="POO",
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

        record = AttendanceRecord(
            session_id=session.id,
            tenant_member_id=uuid4(),
            latitude=-8.0,
            longitude=-34.0,
            distance_meters=10.0,
            within_radius=True,
            record_status=RecordStatus.REGULAR,
            irregularity_flags=[],
        )
        await record_repo.save(record)

        use_case = ReviewAttendanceRecordUseCase(
            record_repo=record_repo,
            session_repo=session_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        with pytest.raises(BusinessRuleException, match="Apenas registros marcados como irregulares"):
            await use_case.execute(
                ReviewAttendanceRecordInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    session_id=session.id,
                    record_id=record.id,
                    user_id=prof_user_id,
                    user_role=UserRole.PROFESSOR,
                    decision=RecordStatus.APPROVED,
                )
            )

    async def test_review_record_raises_403_when_unauthorized(self):
        """Deve lançar ForbiddenException se um aluno tentar revisar um registro."""
        record_repo = FakeAttendanceRecordRepository()
        session_repo = FakeAttendanceSessionRepository()
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)

        aluno_user_id = uuid4()
        aluno_member = TenantMember(tenant_id=tenant.id, user_id=aluno_user_id, role=UserRole.ALUNO)
        await member_repo.save(aluno_member)

        subject_class = SubjectClass(
            tenant_id=tenant.id,
            name="Turma POO",
            discipline_name="POO",
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

        record = AttendanceRecord(
            session_id=session.id,
            tenant_member_id=uuid4(),
            latitude=-8.0,
            longitude=-34.0,
            distance_meters=87.0,
            within_radius=False,
            record_status=RecordStatus.IRREGULAR,
            irregularity_flags=["outside_radius"],
        )
        await record_repo.save(record)

        use_case = ReviewAttendanceRecordUseCase(
            record_repo=record_repo,
            session_repo=session_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )

        with pytest.raises(ForbiddenException):
            await use_case.execute(
                ReviewAttendanceRecordInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    session_id=session.id,
                    record_id=record.id,
                    user_id=aluno_user_id,
                    user_role=UserRole.ALUNO,
                    decision=RecordStatus.APPROVED,
                )
            )
