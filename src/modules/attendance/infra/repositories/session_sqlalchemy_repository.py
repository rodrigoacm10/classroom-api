from datetime import datetime, timezone
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

    async def find_open_session_by_class(
        self, subject_class_id: UUID
    ) -> AttendanceSession | None:
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

    async def list_by_class(
        self, subject_class_id: UUID
    ) -> list[AttendanceSession]:
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

    async def _apply_stats(self, sessions: list[AttendanceSession]) -> None:
        if not sessions:
            return

        subject_class_id = sessions[0].subject_class_id
        session_ids = [item.id for item in sessions]

        total_stmt = select(func.count(EnrollmentModel.id)).where(
            EnrollmentModel.subject_class_id == subject_class_id,
            EnrollmentModel.deleted.is_(False),
            EnrollmentModel.status == EnrollmentStatus.ACTIVE,
        )
        total_students = int((await self.session.execute(total_stmt)).scalar_one() or 0)

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
            item.total_students = total_students
            row = counts_by_session.get(item.id)
            item.confirmed_count = int(row.confirmed_count) if row else 0
            item.irregular_count = int(row.irregular_count) if row else 0

