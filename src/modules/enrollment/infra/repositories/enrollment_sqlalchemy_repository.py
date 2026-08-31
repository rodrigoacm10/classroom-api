from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.enrollment import EnrollmentModel
from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.enrollment.infra.mappers.enrollment_mapper import EnrollmentMapper
from shared.enums.drop_reason import DropReason
from shared.enums.enrollment_status import EnrollmentStatus


class EnrollmentSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, enrollment: Enrollment) -> Enrollment:
        model = EnrollmentMapper.to_model(enrollment)
        merged = await self.session.merge(model)
        await self.session.commit()
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
        await self.session.commit()
        return len(result.fetchall())
