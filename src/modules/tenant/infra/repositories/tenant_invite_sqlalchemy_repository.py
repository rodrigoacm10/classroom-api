from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.tenant_invite import TenantInviteModel
from modules.tenant.domain.entities.tenant_invite import TenantInvite
from modules.tenant.infra.mappers.tenant_invite_mapper import TenantInviteMapper


class TenantInviteSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_id(self, invite_id: UUID) -> TenantInvite | None:
        stmt = select(TenantInviteModel).where(TenantInviteModel.id == invite_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return TenantInviteMapper.to_domain(model) if model else None

    async def find_by_token(self, token: str) -> TenantInvite | None:
        stmt = select(TenantInviteModel).where(TenantInviteModel.token == token)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return TenantInviteMapper.to_domain(model) if model else None

    async def find_by_email_and_tenant(
        self, email: str, tenant_id: UUID
    ) -> TenantInvite | None:
        stmt = select(TenantInviteModel).where(
            TenantInviteModel.email == email,
            TenantInviteModel.tenant_id == tenant_id,
            TenantInviteModel.accepted_at.is_(None),
            TenantInviteModel.revoked_at.is_(None),
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return TenantInviteMapper.to_domain(model) if model else None

    async def save(self, invite: TenantInvite) -> TenantInvite:
        model = TenantInviteMapper.to_model(invite)
        merged = await self.session.merge(model)
        await self.session.commit()
        await self.session.refresh(merged)
        return TenantInviteMapper.to_domain(merged)
