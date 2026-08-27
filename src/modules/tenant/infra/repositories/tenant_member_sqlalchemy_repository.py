from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.tenant import TenantMemberModel
from modules.tenant.domain.entities.tenant_member import TenantMember
from modules.tenant.infra.mappers.tenant_member_mapper import TenantMemberMapper


class TenantMemberSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_tenant_and_user(self, tenant_id: UUID, user_id: UUID) -> TenantMember | None:
        stmt = select(TenantMemberModel).where(
            TenantMemberModel.tenant_id == tenant_id,
            TenantMemberModel.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return TenantMemberMapper.to_domain(model) if model else None

    async def find_by_user_id(self, user_id: UUID) -> list[TenantMember]:
        stmt = select(TenantMemberModel).where(TenantMemberModel.user_id == user_id)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [TenantMemberMapper.to_domain(m) for m in models]

    async def find_by_tenant_id(self, tenant_id: UUID) -> list[TenantMember]:
        stmt = select(TenantMemberModel).where(TenantMemberModel.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [TenantMemberMapper.to_domain(m) for m in models]

    async def save(self, member: TenantMember) -> TenantMember:
        model = TenantMemberMapper.to_model(member)
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return TenantMemberMapper.to_domain(model)
