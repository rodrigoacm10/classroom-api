from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.subject_class import SubjectClassModel
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.infra.mappers.subject_class_mapper import SubjectClassMapper


class SubjectClassSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, subject_class: SubjectClass) -> SubjectClass:
        model = SubjectClassMapper.to_model(subject_class)
        merged = await self.session.merge(model)
        await self.session.commit()
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

    async def delete(self, subject_class: SubjectClass) -> None:
        subject_class.deleted = True
        await self.save(subject_class)
