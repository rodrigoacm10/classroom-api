from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from infra.database.models.attendance_session import AttendanceSessionModel
from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.attendance.infra.mappers.attendance_session_mapper import AttendanceSessionMapper
from shared.enums.session_status import SessionStatus


class SessionSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, session: AttendanceSession) -> AttendanceSession:
        model = AttendanceSessionMapper.to_model(session)
        merged = await self.session.merge(model)
        await self.session.commit()
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
        return AttendanceSessionMapper.to_domain(fetched)

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
        return AttendanceSessionMapper.to_domain(model) if model else None

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
        return AttendanceSessionMapper.to_domain(model) if model else None

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
        return AttendanceSessionMapper.to_domain(model) if model else None

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
        return [AttendanceSessionMapper.to_domain(m) for m in result.scalars().all()]
