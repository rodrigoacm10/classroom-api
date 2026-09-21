from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.attendance_record import AttendanceRecordModel
from infra.database.models.attendance_session import AttendanceSessionModel
from infra.database.models.enrollment import EnrollmentModel
from infra.database.models.room import RoomModel
from infra.database.models.subject_class import SubjectClassModel
from infra.database.models.tenant import TenantMemberModel
from infra.database.models.user import UserModel
from infra.database.models.user_fcm_token import UserFCMTokenModel
from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.enrollment.domain.entities.student_subject_class_summary import (
    StudentSubjectClassSummary,
)
from modules.enrollment.infra.mappers.enrollment_mapper import EnrollmentMapper
from shared.enums.drop_reason import DropReason
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus



class EnrollmentSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, enrollment: Enrollment) -> Enrollment:
        model = EnrollmentMapper.to_model(enrollment)
        merged = await self.session.merge(model)
        await self.session.flush()
        await self.session.refresh(merged)
        return EnrollmentMapper.to_domain(merged)

    async def find_by_id(
        self, enrollment_id: UUID, include_deleted: bool = False
    ) -> Enrollment | None:
        stmt = select(EnrollmentModel).where(EnrollmentModel.id == enrollment_id)
        if not include_deleted:
            stmt = stmt.where(EnrollmentModel.deleted == False)  # noqa: E712
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return EnrollmentMapper.to_domain(model) if model else None

    async def find_by_class_and_member(
        self,
        subject_class_id: UUID,
        tenant_member_id: UUID,
        include_deleted: bool = False,
    ) -> Enrollment | None:
        stmt = select(EnrollmentModel).where(
            EnrollmentModel.subject_class_id == subject_class_id,
            EnrollmentModel.tenant_member_id == tenant_member_id,
        )
        if not include_deleted:
            stmt = stmt.where(EnrollmentModel.deleted == False)  # noqa: E712
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return EnrollmentMapper.to_domain(model) if model else None

    async def list_by_subject_class(
        self,
        subject_class_id: UUID,
        status: EnrollmentStatus | None = None,
        include_deleted: bool = False,
    ) -> list[Enrollment]:
        stmt = select(EnrollmentModel).where(
            EnrollmentModel.subject_class_id == subject_class_id
        )
        if not include_deleted:
            stmt = stmt.where(EnrollmentModel.deleted == False)  # noqa: E712
        if status is not None:
            stmt = stmt.where(EnrollmentModel.status == status)
        result = await self.session.execute(stmt)
        return [EnrollmentMapper.to_domain(m) for m in result.scalars().all()]

    async def list_by_member(
        self,
        tenant_member_id: UUID,
        status: EnrollmentStatus | None = None,
        include_deleted: bool = False,
    ) -> list[Enrollment]:
        stmt = select(EnrollmentModel).where(
            EnrollmentModel.tenant_member_id == tenant_member_id
        )
        if not include_deleted:
            stmt = stmt.where(EnrollmentModel.deleted == False)  # noqa: E712
        if status is not None:
            stmt = stmt.where(EnrollmentModel.status == status)
        result = await self.session.execute(stmt)
        return [EnrollmentMapper.to_domain(m) for m in result.scalars().all()]

    async def list_summaries_by_member(
        self,
        tenant_id: UUID,
        tenant_member_id: UUID,
        status: EnrollmentStatus | None = None,
        include_deleted: bool = False,
    ) -> list[StudentSubjectClassSummary]:
        session_count = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                func.count(AttendanceSessionModel.id).label("session_count"),
            )
            .where(AttendanceSessionModel.status != SessionStatus.CANCELLED)
            .group_by(AttendanceSessionModel.subject_class_id)
            .subquery()
        )
        present_count = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                func.count(AttendanceRecordModel.id).label("present_count"),
            )
            .join(
                AttendanceRecordModel,
                AttendanceRecordModel.session_id == AttendanceSessionModel.id,
            )
            .where(
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
                AttendanceRecordModel.tenant_member_id == tenant_member_id,
                AttendanceRecordModel.record_status.in_(
                    (RecordStatus.REGULAR, RecordStatus.APPROVED)
                ),
            )
            .group_by(AttendanceSessionModel.subject_class_id)
            .subquery()
        )

        stmt = (
            select(
                EnrollmentModel.id,
                EnrollmentModel.subject_class_id,
                EnrollmentModel.status,
                SubjectClassModel.name,
                SubjectClassModel.discipline_name,
                SubjectClassModel.room_id,
                SubjectClassModel.professor_id,
                RoomModel.name,
                UserModel.name,
                func.coalesce(session_count.c.session_count, 0),
                func.coalesce(present_count.c.present_count, 0),
            )
            .join(
                SubjectClassModel,
                SubjectClassModel.id == EnrollmentModel.subject_class_id,
            )
            .outerjoin(RoomModel, RoomModel.id == SubjectClassModel.room_id)
            .outerjoin(
                TenantMemberModel,
                TenantMemberModel.id == SubjectClassModel.professor_id,
            )
            .outerjoin(UserModel, UserModel.id == TenantMemberModel.user_id)
            .outerjoin(
                session_count,
                session_count.c.subject_class_id == SubjectClassModel.id,
            )
            .outerjoin(
                present_count,
                present_count.c.subject_class_id == SubjectClassModel.id,
            )
            .where(
                EnrollmentModel.tenant_member_id == tenant_member_id,
                SubjectClassModel.tenant_id == tenant_id,
            )
        )
        if not include_deleted:
            stmt = stmt.where(
                EnrollmentModel.deleted.is_(False),
                SubjectClassModel.deleted.is_(False),
            )
        if status is not None:
            stmt = stmt.where(EnrollmentModel.status == status)

        result = await self.session.execute(stmt)
        summaries: list[StudentSubjectClassSummary] = []
        for (
            enrollment_id,
            subject_class_id,
            enrollment_status,
            class_name,
            discipline_name,
            room_id,
            professor_id,
            room_name,
            professor_name,
            sessions,
            presents,
        ) in result.all():
            summaries.append(
                StudentSubjectClassSummary(
                    enrollment_id=enrollment_id,
                    subject_class_id=subject_class_id,
                    name=class_name,
                    discipline_name=discipline_name,
                    room_id=room_id,
                    room_name=room_name,
                    professor_id=professor_id,
                    professor_name=professor_name,
                    attendance_rate=StudentSubjectClassSummary.compute_attendance_rate(
                        int(presents), int(sessions)
                    ),
                    status=enrollment_status,
                )
            )
        return summaries

    async def drop_all_active_for_member(self, tenant_member_id: UUID) -> int:
        stmt = (
            update(EnrollmentModel)
            .where(
                EnrollmentModel.tenant_member_id == tenant_member_id,
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                EnrollmentModel.deleted == False,  # noqa: E712
            )
            .values(
                status=EnrollmentStatus.DROPPED,
                dropped_at=func.now(),
                drop_reason=DropReason.ROLE_CHANGE,
            )
            .returning(EnrollmentModel.id)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return len(result.fetchall())

    async def find_active_fcm_tokens(self, subject_class_id: UUID) -> list[str]:
        stmt = (
            select(UserFCMTokenModel.fcm_token)
            .select_from(EnrollmentModel)
            .join(TenantMemberModel, TenantMemberModel.id == EnrollmentModel.tenant_member_id)
            .join(UserFCMTokenModel, UserFCMTokenModel.user_id == TenantMemberModel.user_id)
            .where(
                EnrollmentModel.subject_class_id == subject_class_id,
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                EnrollmentModel.deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

