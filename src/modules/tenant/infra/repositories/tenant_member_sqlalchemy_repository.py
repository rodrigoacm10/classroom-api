from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.tenant import TenantMemberModel
from modules.tenant.domain.entities.tenant_member import TenantMember
from modules.tenant.infra.mappers.tenant_member_mapper import TenantMemberMapper
from shared.enums.user_role import UserRole


class TenantMemberSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_id(
        self, member_id: UUID, include_deleted: bool = False
    ) -> TenantMember | None:
        conditions = [TenantMemberModel.id == member_id]
        if not include_deleted:
            conditions.append(TenantMemberModel.deleted.is_(False))

        stmt = select(TenantMemberModel).where(*conditions)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return TenantMemberMapper.to_domain(model) if model else None

    async def find_by_tenant_and_user(
        self, tenant_id: UUID, user_id: UUID, include_deleted: bool = False
    ) -> TenantMember | None:
        conditions = [
            TenantMemberModel.tenant_id == tenant_id,
            TenantMemberModel.user_id == user_id,
        ]
        if not include_deleted:
            conditions.append(TenantMemberModel.deleted.is_(False))

        stmt = select(TenantMemberModel).where(*conditions)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return TenantMemberMapper.to_domain(model) if model else None

    async def find_by_user_id(
        self, user_id: UUID, include_deleted: bool = False
    ) -> list[TenantMember]:
        conditions = [TenantMemberModel.user_id == user_id]
        if not include_deleted:
            conditions.append(TenantMemberModel.deleted.is_(False))

        stmt = select(TenantMemberModel).where(*conditions)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [TenantMemberMapper.to_domain(m) for m in models]

    async def find_by_tenant_id(
        self, tenant_id: UUID, include_deleted: bool = False
    ) -> list[TenantMember]:
        conditions = [TenantMemberModel.tenant_id == tenant_id]
        if not include_deleted:
            conditions.append(TenantMemberModel.deleted.is_(False))

        stmt = select(TenantMemberModel).where(*conditions)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [TenantMemberMapper.to_domain(m) for m in models]

    async def count_active_admins(self, tenant_id: UUID) -> int:
        stmt = select(func.count(TenantMemberModel.id)).where(
            TenantMemberModel.tenant_id == tenant_id,
            TenantMemberModel.role == UserRole.ADMIN,
            TenantMemberModel.deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def save(self, member: TenantMember) -> TenantMember:
        model = TenantMemberMapper.to_model(member)
        merged_model = await self.session.merge(model)
        await self.session.commit()
        await self.session.refresh(merged_model)
        return TenantMemberMapper.to_domain(merged_model)
