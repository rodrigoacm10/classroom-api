from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.attendance_record import AttendanceRecordModel
from infra.database.models.attendance_session import AttendanceSessionModel
from infra.database.models.enrollment import EnrollmentModel
from infra.database.models.room import RoomModel
from infra.database.models.subject_class import SubjectClassModel
from infra.database.models.tenant import TenantMemberModel
from infra.database.models.user import UserModel
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.entities.subject_class_metrics import SubjectClassMetrics
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

    async def find_summary_by_id_and_tenant(
        self,
        subject_class_id: UUID,
        tenant_id: UUID,
        include_deleted: bool = False,
    ) -> SubjectClassSummary | None:
        enrollment_count = (
            select(
                EnrollmentModel.subject_class_id.label("subject_class_id"),
                func.count(EnrollmentModel.id).label("student_count"),
            )
            .join(SubjectClassModel, SubjectClassModel.id == EnrollmentModel.subject_class_id)
            .where(
                SubjectClassModel.id == subject_class_id,
                SubjectClassModel.tenant_id == tenant_id,
                EnrollmentModel.deleted.is_(False),
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
            )
            .group_by(EnrollmentModel.subject_class_id)
            .subquery()
        )

        session_conditions = [
            SubjectClassModel.id == subject_class_id,
            SubjectClassModel.tenant_id == tenant_id,
            AttendanceSessionModel.status != SessionStatus.CANCELLED,
        ]
        present_conditions = [
            SubjectClassModel.id == subject_class_id,
            SubjectClassModel.tenant_id == tenant_id,
            AttendanceSessionModel.status != SessionStatus.CANCELLED,
            AttendanceRecordModel.record_status.in_((RecordStatus.REGULAR, RecordStatus.APPROVED)),
        ]

        session_count = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                func.count(AttendanceSessionModel.id).label("session_count"),
            )
            .join(
                SubjectClassModel,
                SubjectClassModel.id == AttendanceSessionModel.subject_class_id,
            )
            .where(*session_conditions)
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
            .where(*present_conditions)
            .group_by(AttendanceSessionModel.subject_class_id)
            .subquery()
        )

        active_session_subquery = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                AttendanceSessionModel.id.label("active_session_id"),
            )
            .join(
                SubjectClassModel,
                SubjectClassModel.id == AttendanceSessionModel.subject_class_id,
            )
            .where(
                SubjectClassModel.id == subject_class_id,
                SubjectClassModel.tenant_id == tenant_id,
                AttendanceSessionModel.status == SessionStatus.OPEN,
                AttendanceSessionModel.expires_at > func.now(),
            )
            .distinct(AttendanceSessionModel.subject_class_id)
            .order_by(
                AttendanceSessionModel.subject_class_id,
                AttendanceSessionModel.opened_at.desc(),
            )
            .subquery()
        )

        stmt = (
            select(
                SubjectClassModel,
                UserModel.name,
                RoomModel.name.label("room_name"),
                func.coalesce(enrollment_count.c.student_count, 0),
                func.coalesce(session_count.c.session_count, 0),
                func.coalesce(present_count.c.present_count, 0),
                active_session_subquery.c.active_session_id,
            )
            .outerjoin(
                TenantMemberModel,
                TenantMemberModel.id == SubjectClassModel.professor_id,
            )
            .outerjoin(UserModel, UserModel.id == TenantMemberModel.user_id)
            .outerjoin(RoomModel, RoomModel.id == SubjectClassModel.room_id)
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
            .outerjoin(
                active_session_subquery,
                active_session_subquery.c.subject_class_id == SubjectClassModel.id,
            )
            .where(
                SubjectClassModel.id == subject_class_id,
                SubjectClassModel.tenant_id == tenant_id,
            )
        )
        if not include_deleted:
            stmt = stmt.where(SubjectClassModel.deleted == False)  # noqa: E712

        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            return None

        (
            model,
            professor_name,
            room_name,
            students,
            sessions,
            presents,
            active_session_id,
        ) = row

        student_count = int(students)
        session_total = int(sessions)
        present_total = int(presents)

        return SubjectClassSummary(
            id=model.id,
            tenant_id=model.tenant_id,
            professor_id=model.professor_id,
            professor_name=professor_name,
            room_id=model.room_id,
            room_name=room_name,
            has_active_session=active_session_id is not None,
            active_session_id=active_session_id,
            name=model.name,
            discipline_name=model.discipline_name,
            active=model.active,
            student_count=student_count,
            attendance_rate=SubjectClassSummary.compute_attendance_rate(
                present_total, student_count, session_total
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def list_by_tenant(
        self,
        tenant_id: UUID,
        include_deleted: bool = False,
        active: bool | None = None,
    ) -> list[SubjectClass]:
        stmt = select(SubjectClassModel).where(SubjectClassModel.tenant_id == tenant_id)
        if not include_deleted:
            stmt = stmt.where(SubjectClassModel.deleted == False)  # noqa: E712
        if active is not None:
            stmt = stmt.where(SubjectClassModel.active == active)
        result = await self.session.execute(stmt)
        return [SubjectClassMapper.to_domain(m) for m in result.scalars().all()]

    async def list_summaries_by_tenant(
        self,
        tenant_id: UUID,
        include_deleted: bool = False,
        professor_id: UUID | None = None,
        room_id: UUID | None = None,
        active: bool | None = None,
        days: int | None = None,
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

        session_conditions = [
            SubjectClassModel.tenant_id == tenant_id,
            AttendanceSessionModel.status != SessionStatus.CANCELLED,
        ]
        present_conditions = [
            SubjectClassModel.tenant_id == tenant_id,
            AttendanceSessionModel.status != SessionStatus.CANCELLED,
            AttendanceRecordModel.record_status.in_((RecordStatus.REGULAR, RecordStatus.APPROVED)),
        ]
        if days is not None:
            since = datetime.now(timezone.utc) - timedelta(days=days)
            session_conditions.append(AttendanceSessionModel.opened_at >= since)
            present_conditions.append(AttendanceSessionModel.opened_at >= since)

        session_count = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                func.count(AttendanceSessionModel.id).label("session_count"),
            )
            .join(
                SubjectClassModel,
                SubjectClassModel.id == AttendanceSessionModel.subject_class_id,
            )
            .where(*session_conditions)
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
            .where(*present_conditions)
            .group_by(AttendanceSessionModel.subject_class_id)
            .subquery()
        )

        active_session_subquery = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                AttendanceSessionModel.id.label("active_session_id"),
            )
            .join(
                SubjectClassModel,
                SubjectClassModel.id == AttendanceSessionModel.subject_class_id,
            )
            .where(
                SubjectClassModel.tenant_id == tenant_id,
                AttendanceSessionModel.status == SessionStatus.OPEN,
                AttendanceSessionModel.expires_at > func.now(),
            )
            .distinct(AttendanceSessionModel.subject_class_id)
            .order_by(
                AttendanceSessionModel.subject_class_id,
                AttendanceSessionModel.opened_at.desc(),
            )
            .subquery()
        )

        stmt = (
            select(
                SubjectClassModel,
                UserModel.name,
                RoomModel.name.label("room_name"),
                func.coalesce(enrollment_count.c.student_count, 0),
                func.coalesce(session_count.c.session_count, 0),
                func.coalesce(present_count.c.present_count, 0),
                active_session_subquery.c.active_session_id,
            )
            .outerjoin(
                TenantMemberModel,
                TenantMemberModel.id == SubjectClassModel.professor_id,
            )
            .outerjoin(UserModel, UserModel.id == TenantMemberModel.user_id)
            .outerjoin(RoomModel, RoomModel.id == SubjectClassModel.room_id)
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
            .outerjoin(
                active_session_subquery,
                active_session_subquery.c.subject_class_id == SubjectClassModel.id,
            )
            .where(SubjectClassModel.tenant_id == tenant_id)
        )
        if not include_deleted:
            stmt = stmt.where(SubjectClassModel.deleted.is_(False))
        if active is not None:
            stmt = stmt.where(SubjectClassModel.active == active)
        if professor_id is not None:
            stmt = stmt.where(SubjectClassModel.professor_id == professor_id)
        if room_id is not None:
            stmt = stmt.where(SubjectClassModel.room_id == room_id)

        result = await self.session.execute(stmt)
        summaries: list[SubjectClassSummary] = []
        for (
            model,
            professor_name,
            room_name,
            students,
            sessions,
            presents,
            active_session_id,
        ) in result.all():
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
                    room_name=room_name,
                    has_active_session=active_session_id is not None,
                    active_session_id=active_session_id,
                    name=model.name,
                    discipline_name=model.discipline_name,
                    active=model.active,
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
        active: bool | None = None,
        has_active_session: bool | None = None,
        sort_by: str | None = None,
        order: str | None = None,
    ) -> Page[SubjectClassSummary]:
        active_session_subquery = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                AttendanceSessionModel.id.label("active_session_id"),
            )
            .join(
                SubjectClassModel,
                SubjectClassModel.id == AttendanceSessionModel.subject_class_id,
            )
            .where(
                SubjectClassModel.tenant_id == tenant_id,
                AttendanceSessionModel.status == SessionStatus.OPEN,
                AttendanceSessionModel.expires_at > func.now(),
            )
            .distinct(AttendanceSessionModel.subject_class_id)
            .order_by(
                AttendanceSessionModel.subject_class_id,
                AttendanceSessionModel.opened_at.desc(),
            )
            .subquery()
        )

        conditions = [SubjectClassModel.tenant_id == tenant_id]

        if not include_deleted:
            conditions.append(SubjectClassModel.deleted.is_(False))

        if active is not None:
            conditions.append(SubjectClassModel.active == active)

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

        if has_active_session is True:
            conditions.append(active_session_subquery.c.active_session_id.isnot(None))
        elif has_active_session is False:
            conditions.append(active_session_subquery.c.active_session_id.is_(None))

        count_stmt = (
            select(func.count(SubjectClassModel.id.distinct()))
            .select_from(SubjectClassModel)
            .outerjoin(
                active_session_subquery,
                active_session_subquery.c.subject_class_id == SubjectClassModel.id,
            )
            .where(*conditions)
        )
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

        parsed_sort = (sort_by or "").lower().strip()
        parsed_order = (order or "asc").lower().strip()
        if parsed_sort.endswith("_asc"):
            parsed_sort = parsed_sort[:-4]
            parsed_order = "asc"
        elif parsed_sort.endswith("_desc"):
            parsed_sort = parsed_sort[:-5]
            parsed_order = "desc"

        is_desc = parsed_order == "desc"

        if parsed_sort in ("name",):
            order_exprs = [
                SubjectClassModel.name.desc() if is_desc else SubjectClassModel.name.asc()
            ]
        elif parsed_sort in ("discipline", "discipline_name"):
            order_exprs = [
                SubjectClassModel.discipline_name.desc()
                if is_desc
                else SubjectClassModel.discipline_name.asc()
            ]
        elif parsed_sort in ("students", "student_count"):
            order_exprs = [
                func.coalesce(enrollment_count.c.student_count, 0).desc()
                if is_desc
                else func.coalesce(enrollment_count.c.student_count, 0).asc(),
                SubjectClassModel.name.asc(),
            ]
        elif parsed_sort in ("created_at",):
            order_exprs = [
                SubjectClassModel.created_at.desc()
                if is_desc
                else SubjectClassModel.created_at.asc()
            ]
        else:
            order_exprs = [SubjectClassModel.created_at.desc()]

        stmt = (
            select(
                SubjectClassModel,
                UserModel.name,
                RoomModel.name.label("room_name"),
                func.coalesce(enrollment_count.c.student_count, 0),
                func.coalesce(session_count.c.session_count, 0),
                func.coalesce(present_count.c.present_count, 0),
                active_session_subquery.c.active_session_id,
            )
            .outerjoin(
                TenantMemberModel,
                TenantMemberModel.id == SubjectClassModel.professor_id,
            )
            .outerjoin(UserModel, UserModel.id == TenantMemberModel.user_id)
            .outerjoin(RoomModel, RoomModel.id == SubjectClassModel.room_id)
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
            .outerjoin(
                active_session_subquery,
                active_session_subquery.c.subject_class_id == SubjectClassModel.id,
            )
            .where(*conditions)
            .order_by(*order_exprs)
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )

        result = await self.session.execute(stmt)
        summaries: list[SubjectClassSummary] = []
        for (
            model,
            professor_name,
            room_name,
            students,
            sessions,
            presents,
            active_session_id,
        ) in result.all():
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
                    room_name=room_name,
                    has_active_session=active_session_id is not None,
                    active_session_id=active_session_id,
                    name=model.name,
                    discipline_name=model.discipline_name,
                    active=model.active,
                    student_count=student_count,
                    attendance_rate=SubjectClassSummary.compute_attendance_rate(
                        present_total, student_count, session_total
                    ),
                    created_at=model.created_at,
                    updated_at=model.updated_at,
                )
            )
        return Page.from_params(summaries, total=total, pagination=pagination)

    async def get_metrics_by_tenant(
        self,
        tenant_id: UUID,
        professor_id: UUID | None = None,
        days: int | None = None,
    ) -> SubjectClassMetrics:
        summaries = await self.list_summaries_by_tenant(
            tenant_id=tenant_id,
            professor_id=professor_id,
            days=days,
        )
        total_classes = len(summaries)
        active_classes = sum(1 for s in summaries if s.active)
        inactive_classes = total_classes - active_classes
        total_students = sum(s.student_count for s in summaries)
        active_summaries = [s for s in summaries if s.active]
        avg_attendance = (
            round(sum(s.attendance_rate for s in active_summaries) / len(active_summaries), 4)
            if active_summaries
            else 0.0
        )
        at_risk_count = sum(1 for s in active_summaries if s.attendance_rate < 0.75)
        live_classes_count = sum(1 for s in summaries if s.has_active_session)

        return SubjectClassMetrics(
            total_classes=total_classes,
            active_classes=active_classes,
            inactive_classes=inactive_classes,
            total_students=total_students,
            average_attendance_rate=avg_attendance,
            at_risk_classes_count=at_risk_count,
            live_classes_count=live_classes_count,
        )

    async def delete(self, subject_class: SubjectClass) -> None:
        subject_class.deleted = True
        await self.save(subject_class)
