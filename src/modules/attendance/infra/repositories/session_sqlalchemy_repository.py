from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from infra.database.models.attendance_record import AttendanceRecordModel
from infra.database.models.attendance_session import AttendanceSessionModel
from infra.database.models.enrollment import EnrollmentModel
from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.attendance.infra.mappers.attendance_session_mapper import AttendanceSessionMapper
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.pagination import Page, PaginationParams


class SessionSQLAlchemyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, session: AttendanceSession) -> AttendanceSession:
        model = AttendanceSessionMapper.to_model(session)
        merged = await self.session.merge(model)
        await self.session.flush()
        await self.session.refresh(merged)

        # Refetch with relations
        stmt = (
            select(AttendanceSessionModel)
            .options(
                joinedload(AttendanceSessionModel.subject_class),
                joinedload(AttendanceSessionModel.room),
            )
            .where(AttendanceSessionModel.id == merged.id)
        )
        result = await self.session.execute(stmt)
        fetched = result.scalar_one()
        session = AttendanceSessionMapper.to_domain(fetched)
        await self._apply_stats([session])
        return session

    async def find_by_id(self, session_id: UUID) -> AttendanceSession | None:
        stmt = (
            select(AttendanceSessionModel)
            .options(
                joinedload(AttendanceSessionModel.subject_class),
                joinedload(AttendanceSessionModel.room),
            )
            .where(AttendanceSessionModel.id == session_id)
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        session = AttendanceSessionMapper.to_domain(model)
        await self._apply_stats([session])
        return session

    async def find_by_id_and_class(
        self, session_id: UUID, subject_class_id: UUID
    ) -> AttendanceSession | None:
        stmt = (
            select(AttendanceSessionModel)
            .options(
                joinedload(AttendanceSessionModel.subject_class),
                joinedload(AttendanceSessionModel.room),
            )
            .where(
                AttendanceSessionModel.id == session_id,
                AttendanceSessionModel.subject_class_id == subject_class_id,
            )
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        session = AttendanceSessionMapper.to_domain(model)
        await self._apply_stats([session])
        return session

    async def find_open_session_by_class(self, subject_class_id: UUID) -> AttendanceSession | None:
        stmt = (
            select(AttendanceSessionModel)
            .options(
                joinedload(AttendanceSessionModel.subject_class),
                joinedload(AttendanceSessionModel.room),
            )
            .where(
                AttendanceSessionModel.subject_class_id == subject_class_id,
                AttendanceSessionModel.status == SessionStatus.OPEN,
            )
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        session = AttendanceSessionMapper.to_domain(model)
        await self._apply_stats([session])
        return session

    async def list_by_class(self, subject_class_id: UUID) -> list[AttendanceSession]:
        stmt = (
            select(AttendanceSessionModel)
            .options(
                joinedload(AttendanceSessionModel.subject_class),
                joinedload(AttendanceSessionModel.room),
            )
            .where(AttendanceSessionModel.subject_class_id == subject_class_id)
            .order_by(AttendanceSessionModel.opened_at.desc())
        )
        result = await self.session.execute(stmt)
        sessions = [AttendanceSessionMapper.to_domain(m) for m in result.scalars().all()]
        await self._apply_stats(sessions)
        return sessions

    async def find_by_class_paginated(
        self,
        subject_class_id: UUID,
        pagination: PaginationParams,
        status: SessionStatus | None = None,
        opened_after: datetime | None = None,
        opened_before: datetime | None = None,
    ) -> Page[AttendanceSession]:
        conditions = [AttendanceSessionModel.subject_class_id == subject_class_id]

        if status is not None:
            conditions.append(AttendanceSessionModel.status == status)

        if opened_after is not None:
            conditions.append(AttendanceSessionModel.opened_at >= opened_after)

        if opened_before is not None:
            conditions.append(AttendanceSessionModel.opened_at <= opened_before)

        count_stmt = select(func.count(AttendanceSessionModel.id)).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one() or 0

        items_stmt = (
            select(AttendanceSessionModel)
            .options(
                joinedload(AttendanceSessionModel.subject_class),
                joinedload(AttendanceSessionModel.room),
            )
            .where(*conditions)
            .order_by(AttendanceSessionModel.opened_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
        result = await self.session.execute(items_stmt)
        sessions = [AttendanceSessionMapper.to_domain(m) for m in result.scalars().all()]
        await self._apply_stats(sessions)

        return Page.from_params(sessions, total=total, pagination=pagination)

    async def close_expired_sessions(self) -> list[AttendanceSession]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(AttendanceSessionModel)
            .options(
                joinedload(AttendanceSessionModel.subject_class),
                joinedload(AttendanceSessionModel.room),
            )
            .where(
                AttendanceSessionModel.status == SessionStatus.OPEN,
                AttendanceSessionModel.expires_at <= now,
            )
        )
        result = await self.session.execute(stmt)
        expired_models = result.scalars().all()

        closed_sessions: list[AttendanceSession] = []
        for model in expired_models:
            model.status = SessionStatus.CLOSED
            closed_sessions.append(AttendanceSessionMapper.to_domain(model))

        await self.session.flush()
        return closed_sessions

    async def list_active_sessions_by_tenant(
        self,
        tenant_id: UUID,
        professor_user_id: UUID | None = None,
    ) -> list[AttendanceSession]:
        from infra.database.models.subject_class import SubjectClassModel
        from infra.database.models.tenant import TenantMemberModel

        now = datetime.now(timezone.utc)
        stmt = (
            select(AttendanceSessionModel)
            .options(
                joinedload(AttendanceSessionModel.subject_class),
                joinedload(AttendanceSessionModel.room),
            )
            .join(
                SubjectClassModel,
                SubjectClassModel.id == AttendanceSessionModel.subject_class_id,
            )
            .where(
                SubjectClassModel.tenant_id == tenant_id,
                SubjectClassModel.deleted.is_(False),
                SubjectClassModel.active.is_(True),
                AttendanceSessionModel.status == SessionStatus.OPEN,
                AttendanceSessionModel.expires_at > now,
            )
        )

        if professor_user_id is not None:
            stmt = stmt.join(
                TenantMemberModel,
                TenantMemberModel.id == SubjectClassModel.professor_id,
            ).where(
                TenantMemberModel.user_id == professor_user_id,
                TenantMemberModel.deleted.is_(False),
            )

        stmt = stmt.order_by(AttendanceSessionModel.opened_at.desc())

        result = await self.session.execute(stmt)
        models = result.scalars().all()
        if not models:
            return []

        sessions = [AttendanceSessionMapper.to_domain(m) for m in models]
        await self._apply_stats(sessions)
        return sessions

    async def list_by_tenant_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        professor_user_id: UUID | None = None,
        subject_class_id: UUID | None = None,
        status: SessionStatus | None = None,
        exclude_status: SessionStatus | None = None,
        opened_after: datetime | None = None,
        opened_before: datetime | None = None,
        search: str | None = None,
    ) -> Page[AttendanceSession]:
        from infra.database.models.subject_class import SubjectClassModel
        from infra.database.models.tenant import TenantMemberModel

        conditions = [
            SubjectClassModel.tenant_id == tenant_id,
            SubjectClassModel.deleted.is_(False),
        ]

        if subject_class_id is not None:
            conditions.append(AttendanceSessionModel.subject_class_id == subject_class_id)

        if status is not None:
            conditions.append(AttendanceSessionModel.status == status)

        if exclude_status is not None:
            conditions.append(AttendanceSessionModel.status != exclude_status)

        if opened_after is not None:
            conditions.append(AttendanceSessionModel.opened_at >= opened_after)

        if opened_before is not None:
            conditions.append(AttendanceSessionModel.opened_at <= opened_before)

        if search and search.strip():
            term = f"%{search.strip()}%"
            conditions.append(
                (SubjectClassModel.name.ilike(term))
                | (SubjectClassModel.discipline_name.ilike(term))
            )

        base_from = select(func.count(AttendanceSessionModel.id)).join(
            SubjectClassModel,
            SubjectClassModel.id == AttendanceSessionModel.subject_class_id,
        )

        if professor_user_id is not None:
            base_from = base_from.join(
                TenantMemberModel,
                TenantMemberModel.id == SubjectClassModel.professor_id,
            )
            conditions.extend(
                [
                    TenantMemberModel.user_id == professor_user_id,
                    TenantMemberModel.deleted.is_(False),
                ]
            )

        count_stmt = base_from.where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one() or 0

        items_stmt = (
            select(AttendanceSessionModel)
            .options(
                joinedload(AttendanceSessionModel.subject_class),
                joinedload(AttendanceSessionModel.room),
            )
            .join(
                SubjectClassModel,
                SubjectClassModel.id == AttendanceSessionModel.subject_class_id,
            )
        )

        if professor_user_id is not None:
            items_stmt = items_stmt.join(
                TenantMemberModel,
                TenantMemberModel.id == SubjectClassModel.professor_id,
            )

        items_stmt = (
            items_stmt.where(*conditions)
            .order_by(AttendanceSessionModel.opened_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )

        result = await self.session.execute(items_stmt)
        models = result.scalars().all()
        sessions = [AttendanceSessionMapper.to_domain(m) for m in models]
        await self._apply_stats(sessions)

        return Page.from_params(sessions, total=total, pagination=pagination)

    async def get_metrics_by_tenant(
        self,
        tenant_id: UUID,
        professor_user_id: UUID | None = None,
        days: int = 30,
    ) -> dict:
        from infra.database.models.subject_class import SubjectClassModel
        from infra.database.models.tenant import TenantMemberModel

        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)

        class_conditions = [
            SubjectClassModel.tenant_id == tenant_id,
            SubjectClassModel.deleted.is_(False),
        ]
        class_query = select(SubjectClassModel.id)
        if professor_user_id is not None:
            class_query = class_query.join(
                TenantMemberModel,
                TenantMemberModel.id == SubjectClassModel.professor_id,
            )
            class_conditions.extend(
                [
                    TenantMemberModel.user_id == professor_user_id,
                    TenantMemberModel.deleted.is_(False),
                ]
            )
        class_ids = (
            (await self.session.execute(class_query.where(*class_conditions))).scalars().all()
        )

        if not class_ids:
            return {
                "total_sessions": 0,
                "average_attendance_rate": 0.0,
                "cancelled_sessions": 0,
                "last_session": None,
            }

        # 1. Total sessions in the last N days
        total_stmt = select(func.count(AttendanceSessionModel.id)).where(
            AttendanceSessionModel.subject_class_id.in_(class_ids),
            AttendanceSessionModel.opened_at >= since,
        )
        total_sessions = (await self.session.execute(total_stmt)).scalar_one() or 0

        # 2. Cancelled sessions in the last N days
        cancelled_stmt = select(func.count(AttendanceSessionModel.id)).where(
            AttendanceSessionModel.subject_class_id.in_(class_ids),
            AttendanceSessionModel.status == SessionStatus.CANCELLED,
            AttendanceSessionModel.opened_at >= since,
        )
        cancelled_sessions = (await self.session.execute(cancelled_stmt)).scalar_one() or 0

        # 3. Average attendance rate across non-cancelled sessions in the last N days
        sessions_stmt = (
            select(AttendanceSessionModel)
            .options(
                joinedload(AttendanceSessionModel.subject_class),
                joinedload(AttendanceSessionModel.room),
            )
            .where(
                AttendanceSessionModel.subject_class_id.in_(class_ids),
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
                AttendanceSessionModel.opened_at >= since,
            )
        )
        period_models = (await self.session.execute(sessions_stmt)).scalars().all()
        period_sessions = [AttendanceSessionMapper.to_domain(m) for m in period_models]
        await self._apply_stats(period_sessions)

        valid_sessions = [s for s in period_sessions if s.total_students > 0]
        if valid_sessions:
            total_rate = sum((s.confirmed_count / s.total_students) for s in valid_sessions)
            avg_rate = round(total_rate / len(valid_sessions), 4)
        else:
            avg_rate = 0.0

        # 4. Last session performed
        last_stmt = (
            select(AttendanceSessionModel)
            .options(
                joinedload(AttendanceSessionModel.subject_class),
                joinedload(AttendanceSessionModel.room),
            )
            .where(AttendanceSessionModel.subject_class_id.in_(class_ids))
            .order_by(AttendanceSessionModel.opened_at.desc())
            .limit(1)
        )
        last_model = (await self.session.execute(last_stmt)).scalar_one_or_none()
        last_session_dict = None
        if last_model:
            last_domain = AttendanceSessionMapper.to_domain(last_model)
            await self._apply_stats([last_domain])
            rate = (
                round(last_domain.confirmed_count / last_domain.total_students, 4)
                if last_domain.total_students > 0
                else 0.0
            )
            last_session_dict = {
                "id": last_domain.id,
                "subject_class_id": last_domain.subject_class_id,
                "subject_class_name": last_domain.subject_class.name
                if last_domain.subject_class
                else "",
                "discipline_name": last_domain.subject_class.discipline_name
                if last_domain.subject_class
                else "",
                "room_name": last_domain.room.name if last_domain.room else None,
                "opened_at": last_domain.opened_at,
                "day_code": last_domain.day_code,
                "status": last_domain.status,
                "confirmed_count": last_domain.confirmed_count,
                "total_students": last_domain.total_students,
                "attendance_rate": rate,
            }

        return {
            "total_sessions": total_sessions,
            "average_attendance_rate": avg_rate,
            "cancelled_sessions": cancelled_sessions,
            "last_session": last_session_dict,
        }

    async def _apply_stats(self, sessions: list[AttendanceSession]) -> None:
        if not sessions:
            return

        class_ids = list({item.subject_class_id for item in sessions})
        session_ids = [item.id for item in sessions]

        total_stmt = (
            select(
                EnrollmentModel.subject_class_id,
                func.count(EnrollmentModel.id).label("student_count"),
            )
            .where(
                EnrollmentModel.subject_class_id.in_(class_ids),
                EnrollmentModel.deleted.is_(False),
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
            )
            .group_by(EnrollmentModel.subject_class_id)
        )
        total_by_class = {
            row.subject_class_id: int(row.student_count)
            for row in (await self.session.execute(total_stmt)).all()
        }

        counts_stmt = (
            select(
                AttendanceRecordModel.session_id,
                func.count(AttendanceRecordModel.id).label("confirmed_count"),
                func.coalesce(
                    func.sum(
                        case(
                            (AttendanceRecordModel.record_status == RecordStatus.IRREGULAR, 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("irregular_count"),
            )
            .where(AttendanceRecordModel.session_id.in_(session_ids))
            .group_by(AttendanceRecordModel.session_id)
        )
        counts_by_session = {
            row.session_id: row for row in (await self.session.execute(counts_stmt)).all()
        }

        for item in sessions:
            item.total_students = total_by_class.get(item.subject_class_id, 0)
            row = counts_by_session.get(item.id)
            item.confirmed_count = int(row.confirmed_count) if row else 0
            item.irregular_count = int(row.irregular_count) if row else 0
