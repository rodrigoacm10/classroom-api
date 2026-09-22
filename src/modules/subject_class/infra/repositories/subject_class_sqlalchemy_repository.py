from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.attendance_record import AttendanceRecordModel
from infra.database.models.attendance_session import AttendanceSessionModel
from infra.database.models.enrollment import EnrollmentModel
from infra.database.models.subject_class import SubjectClassModel
from infra.database.models.tenant import TenantMemberModel
from infra.database.models.user import UserModel
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.entities.subject_class_summary import SubjectClassSummary
from modules.subject_class.infra.mappers.subject_class_mapper import SubjectClassMapper
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.pagination import Page, PaginationParams


class SubjectClassSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, subject_class: SubjectClass) -> SubjectClass:
        model = SubjectClassMapper.to_model(subject_class)
        merged = await self.session.merge(model)
        await self.session.flush()
        await self.session.refresh(merged)
        return SubjectClassMapper.to_domain(merged)

    async def find_by_id(
        self, subject_class_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None:
        stmt = select(SubjectClassModel).where(SubjectClassModel.id == subject_class_id)
        if not include_deleted:
            stmt = stmt.where(SubjectClassModel.deleted == False)  # noqa: E712
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return SubjectClassMapper.to_domain(model) if model else None

    async def find_by_id_and_tenant(
        self, subject_class_id: UUID, tenant_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None:
        stmt = select(SubjectClassModel).where(
            SubjectClassModel.id == subject_class_id,
            SubjectClassModel.tenant_id == tenant_id,
        )
        if not include_deleted:
            stmt = stmt.where(SubjectClassModel.deleted == False)  # noqa: E712
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return SubjectClassMapper.to_domain(model) if model else None

    async def list_by_tenant(
        self, tenant_id: UUID, include_deleted: bool = False
    ) -> list[SubjectClass]:
        stmt = select(SubjectClassModel).where(SubjectClassModel.tenant_id == tenant_id)
        if not include_deleted:
            stmt = stmt.where(SubjectClassModel.deleted == False)  # noqa: E712
        result = await self.session.execute(stmt)
        return [SubjectClassMapper.to_domain(m) for m in result.scalars().all()]

    async def list_summaries_by_tenant(
        self,
        tenant_id: UUID,
        include_deleted: bool = False,
        professor_id: UUID | None = None,
        room_id: UUID | None = None,
    ) -> list[SubjectClassSummary]:
        enrollment_count = (
            select(
                EnrollmentModel.subject_class_id.label("subject_class_id"),
                func.count(EnrollmentModel.id).label("student_count"),
            )
            .join(SubjectClassModel, SubjectClassModel.id == EnrollmentModel.subject_class_id)
            .where(
                SubjectClassModel.tenant_id == tenant_id,
                EnrollmentModel.deleted.is_(False),
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
            )
            .group_by(EnrollmentModel.subject_class_id)
            .subquery()
        )
        session_count = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                func.count(AttendanceSessionModel.id).label("session_count"),
            )
            .join(
                SubjectClassModel,
                SubjectClassModel.id == AttendanceSessionModel.subject_class_id,
            )
            .where(
                SubjectClassModel.tenant_id == tenant_id,
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
            )
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
            .join(
                EnrollmentModel,
                and_(
                    EnrollmentModel.subject_class_id == AttendanceSessionModel.subject_class_id,
                    EnrollmentModel.tenant_member_id == AttendanceRecordModel.tenant_member_id,
                    EnrollmentModel.deleted.is_(False),
                    EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                ),
            )
            .join(
                SubjectClassModel,
                SubjectClassModel.id == AttendanceSessionModel.subject_class_id,
            )
            .where(
                SubjectClassModel.tenant_id == tenant_id,
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
                AttendanceRecordModel.record_status.in_(
                    (RecordStatus.REGULAR, RecordStatus.APPROVED)
                ),
            )
            .group_by(AttendanceSessionModel.subject_class_id)
            .subquery()
        )

        stmt = (
            select(
                SubjectClassModel,
                UserModel.name,
                func.coalesce(enrollment_count.c.student_count, 0),
                func.coalesce(session_count.c.session_count, 0),
                func.coalesce(present_count.c.present_count, 0),
            )
            .outerjoin(
                TenantMemberModel,
                TenantMemberModel.id == SubjectClassModel.professor_id,
            )
            .outerjoin(UserModel, UserModel.id == TenantMemberModel.user_id)
            .outerjoin(
                enrollment_count,
                enrollment_count.c.subject_class_id == SubjectClassModel.id,
            )
            .outerjoin(
                session_count,
                session_count.c.subject_class_id == SubjectClassModel.id,
            )
            .outerjoin(
                present_count,
                present_count.c.subject_class_id == SubjectClassModel.id,
            )
            .where(SubjectClassModel.tenant_id == tenant_id)
        )
        if not include_deleted:
            stmt = stmt.where(SubjectClassModel.deleted.is_(False))
        if professor_id is not None:
            stmt = stmt.where(SubjectClassModel.professor_id == professor_id)
        if room_id is not None:
            stmt = stmt.where(SubjectClassModel.room_id == room_id)

        result = await self.session.execute(stmt)
        summaries: list[SubjectClassSummary] = []
        for model, professor_name, students, sessions, presents in result.all():
            student_count = int(students)
            session_total = int(sessions)
            present_total = int(presents)
            summaries.append(
                SubjectClassSummary(
                    id=model.id,
                    tenant_id=model.tenant_id,
                    professor_id=model.professor_id,
                    professor_name=professor_name,
                    room_id=model.room_id,
                    name=model.name,
                    discipline_name=model.discipline_name,
                    student_count=student_count,
                    attendance_rate=SubjectClassSummary.compute_attendance_rate(
                        present_total, student_count, session_total
                    ),
                    created_at=model.created_at,
                    updated_at=model.updated_at,
                )
            )
        return summaries

    async def find_summaries_by_tenant_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        include_deleted: bool = False,
        professor_id: UUID | None = None,
        room_id: UUID | None = None,
        search: str | None = None,
    ) -> Page[SubjectClassSummary]:
        conditions = [SubjectClassModel.tenant_id == tenant_id]

        if not include_deleted:
            conditions.append(SubjectClassModel.deleted.is_(False))

        if professor_id is not None:
            conditions.append(SubjectClassModel.professor_id == professor_id)

        if room_id is not None:
            conditions.append(SubjectClassModel.room_id == room_id)

        if search:
            conditions.append(
                or_(
                    SubjectClassModel.name.ilike(f"%{search}%"),
                    SubjectClassModel.discipline_name.ilike(f"%{search}%"),
                )
            )

        count_stmt = select(func.count(SubjectClassModel.id)).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one() or 0

        enrollment_count = (
            select(
                EnrollmentModel.subject_class_id.label("subject_class_id"),
                func.count(EnrollmentModel.id).label("student_count"),
            )
            .join(SubjectClassModel, SubjectClassModel.id == EnrollmentModel.subject_class_id)
            .where(
                SubjectClassModel.tenant_id == tenant_id,
                EnrollmentModel.deleted.is_(False),
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
            )
            .group_by(EnrollmentModel.subject_class_id)
            .subquery()
        )
        session_count = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                func.count(AttendanceSessionModel.id).label("session_count"),
            )
            .join(
                SubjectClassModel,
                SubjectClassModel.id == AttendanceSessionModel.subject_class_id,
            )
            .where(
                SubjectClassModel.tenant_id == tenant_id,
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
            )
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
            .join(
                EnrollmentModel,
                and_(
                    EnrollmentModel.subject_class_id == AttendanceSessionModel.subject_class_id,
                    EnrollmentModel.tenant_member_id == AttendanceRecordModel.tenant_member_id,
                    EnrollmentModel.deleted.is_(False),
                    EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                ),
            )
            .join(
                SubjectClassModel,
                SubjectClassModel.id == AttendanceSessionModel.subject_class_id,
            )
            .where(
                SubjectClassModel.tenant_id == tenant_id,
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
                AttendanceRecordModel.record_status.in_(
                    (RecordStatus.REGULAR, RecordStatus.APPROVED)
                ),
            )
            .group_by(AttendanceSessionModel.subject_class_id)
            .subquery()
        )

        stmt = (
            select(
                SubjectClassModel,
                UserModel.name,
                func.coalesce(enrollment_count.c.student_count, 0),
                func.coalesce(session_count.c.session_count, 0),
                func.coalesce(present_count.c.present_count, 0),
            )
            .outerjoin(
                TenantMemberModel,
                TenantMemberModel.id == SubjectClassModel.professor_id,
            )
            .outerjoin(UserModel, UserModel.id == TenantMemberModel.user_id)
            .outerjoin(
                enrollment_count,
                enrollment_count.c.subject_class_id == SubjectClassModel.id,
            )
            .outerjoin(
                session_count,
                session_count.c.subject_class_id == SubjectClassModel.id,
            )
            .outerjoin(
                present_count,
                present_count.c.subject_class_id == SubjectClassModel.id,
            )
            .where(*conditions)
            .order_by(SubjectClassModel.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )

        result = await self.session.execute(stmt)
        summaries: list[SubjectClassSummary] = []
        for model, professor_name, students, sessions, presents in result.all():
            student_count = int(students)
            session_total = int(sessions)
            present_total = int(presents)
            summaries.append(
                SubjectClassSummary(
                    id=model.id,
                    tenant_id=model.tenant_id,
                    professor_id=model.professor_id,
                    professor_name=professor_name,
                    room_id=model.room_id,
                    name=model.name,
                    discipline_name=model.discipline_name,
                    student_count=student_count,
                    attendance_rate=SubjectClassSummary.compute_attendance_rate(
                        present_total, student_count, session_total
                    ),
                    created_at=model.created_at,
                    updated_at=model.updated_at,
                )
            )
        return Page.from_params(summaries, total=total, pagination=pagination)

    async def delete(self, subject_class: SubjectClass) -> None:
        subject_class.deleted = True
        await self.save(subject_class)
