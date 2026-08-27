from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.tenant import TenantModel
from modules.tenant.domain.entities.tenant import Tenant
from modules.tenant.infra.mappers.tenant_mapper import TenantMapper


class TenantSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_id(self, tenant_id: UUID, include_deleted: bool = False) -> Tenant | None:
        stmt = select(TenantModel).where(TenantModel.id == tenant_id)
        if not include_deleted:
            stmt = stmt.where(TenantModel.deleted == False)  # noqa: E712
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return TenantMapper.to_domain(model) if model else None

    async def find_by_slug(self, slug: str, include_deleted: bool = False) -> Tenant | None:
        stmt = select(TenantModel).where(TenantModel.slug == slug)
        if not include_deleted:
            stmt = stmt.where(TenantModel.deleted == False)  # noqa: E712
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return TenantMapper.to_domain(model) if model else None

    async def save(self, tenant: Tenant) -> Tenant:
        model = TenantMapper.to_model(tenant)
        merged_model = await self.session.merge(model)
        await self.session.commit()
        await self.session.refresh(merged_model)
        return TenantMapper.to_domain(merged_model)
