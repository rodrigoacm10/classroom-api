from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.enrollment import EnrollmentModel
from infra.database.models.tenant import TenantMemberModel
from infra.database.models.user import UserModel
from modules.tenant.domain.entities.tenant_member import TenantMember
from modules.tenant.infra.mappers.tenant_member_mapper import TenantMemberMapper
from shared.enums.user_role import UserRole


from shared.pagination import Page, PaginationParams


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
        self,
        tenant_id: UUID,
        user_id: UUID,
        include_deleted: bool = False,
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

    async def find_by_tenant_id_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        role: UserRole | None = None,
        search: str | None = None,
        subject_class_id: UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        include_deleted: bool = False,
    ) -> Page[TenantMember]:
        conditions = [TenantMemberModel.tenant_id == tenant_id]
        if role is not None:
            conditions.append(TenantMemberModel.role == role)
        if created_after is not None:
            conditions.append(TenantMemberModel.created_at >= created_after)
        if created_before is not None:
            conditions.append(TenantMemberModel.created_at <= created_before)
        if not include_deleted:
            conditions.append(TenantMemberModel.deleted.is_(False))

        # Query de contagem total
        count_stmt = select(func.count(func.distinct(TenantMemberModel.id))).where(*conditions)
        if search:
            count_stmt = count_stmt.join(UserModel, UserModel.id == TenantMemberModel.user_id).where(
                or_(
                    UserModel.name.ilike(f"%{search}%"),
                    UserModel.email.ilike(f"%{search}%"),
                )
            )
        if subject_class_id:
            count_stmt = count_stmt.join(
                EnrollmentModel,
                and_(
                    EnrollmentModel.tenant_member_id == TenantMemberModel.id,
                    EnrollmentModel.deleted.is_(False),
                ),
            ).where(EnrollmentModel.subject_class_id == subject_class_id)

        total = int((await self.session.execute(count_stmt)).scalar_one() or 0)

        # Query dos itens paginados
        items_stmt = select(TenantMemberModel).where(*conditions)
        if search:
            items_stmt = items_stmt.join(UserModel, UserModel.id == TenantMemberModel.user_id).where(
                or_(
                    UserModel.name.ilike(f"%{search}%"),
                    UserModel.email.ilike(f"%{search}%"),
                )
            )
        if subject_class_id:
            items_stmt = items_stmt.join(
                EnrollmentModel,
                and_(
                    EnrollmentModel.tenant_member_id == TenantMemberModel.id,
                    EnrollmentModel.deleted.is_(False),
                ),
            ).where(EnrollmentModel.subject_class_id == subject_class_id)

        items_stmt = (
            items_stmt.order_by(TenantMemberModel.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )

        result = await self.session.execute(items_stmt)
        models = result.scalars().all()
        items = [TenantMemberMapper.to_domain(m) for m in models]

        return Page.from_params(items, total=total, pagination=pagination)

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
        await self.session.flush()
        await self.session.refresh(merged_model)
        return TenantMemberMapper.to_domain(merged_model)
