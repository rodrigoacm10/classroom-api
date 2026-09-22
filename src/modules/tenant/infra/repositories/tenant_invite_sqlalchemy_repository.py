from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.tenant_invite import TenantInviteModel
from modules.tenant.domain.entities.tenant_invite import TenantInvite
from modules.tenant.infra.mappers.tenant_invite_mapper import TenantInviteMapper
from shared.enums.user_role import UserRole
from shared.pagination import Page, PaginationParams


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

    async def find_by_tenant_id_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        status: str | None = None,
        role: UserRole | None = None,
        search: str | None = None,
    ) -> Page[TenantInvite]:
        conditions = [TenantInviteModel.tenant_id == tenant_id]

        if role is not None:
            conditions.append(TenantInviteModel.role == role)

        if search:
            conditions.append(TenantInviteModel.email.ilike(f"%{search}%"))

        if status:
            st = status.lower()
            now_expr = func.now()
            if st == "pending":
                conditions.extend([
                    TenantInviteModel.accepted_at.is_(None),
                    TenantInviteModel.revoked_at.is_(None),
                    TenantInviteModel.expires_at > now_expr,
                ])
            elif st == "accepted":
                conditions.append(TenantInviteModel.accepted_at.is_not(None))
            elif st == "revoked":
                conditions.append(TenantInviteModel.revoked_at.is_not(None))
            elif st == "expired":
                conditions.extend([
                    TenantInviteModel.accepted_at.is_(None),
                    TenantInviteModel.revoked_at.is_(None),
                    TenantInviteModel.expires_at <= now_expr,
                ])

        count_stmt = select(func.count(TenantInviteModel.id)).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one() or 0

        items_stmt = (
            select(TenantInviteModel)
            .where(*conditions)
            .order_by(TenantInviteModel.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )

        result = await self.session.execute(items_stmt)
        models = result.scalars().all()
        items = [TenantInviteMapper.to_domain(m) for m in models]

        return Page.from_params(items, total=total, pagination=pagination)

    async def save(self, invite: TenantInvite) -> TenantInvite:
        model = TenantInviteMapper.to_model(invite)
        merged = await self.session.merge(model)
        await self.session.flush()
        await self.session.refresh(merged)
        return TenantInviteMapper.to_domain(merged)
