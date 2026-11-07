from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.subject_class import SubjectClassModel
from infra.database.models.tenant_invite import TenantInviteModel
from infra.database.models.user import UserModel
from modules.tenant.domain.entities.tenant_invite import (
    TenantInvite,
    TenantInvitesMetrics,
)
from modules.tenant.infra.mappers.tenant_invite_mapper import TenantInviteMapper
from shared.enums.user_role import UserRole
from shared.pagination import Page, PaginationParams


class TenantInviteSQLAlchemyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_id(self, invite_id: UUID) -> TenantInvite | None:
        stmt = (
            select(TenantInviteModel, UserModel.name)
            .outerjoin(UserModel, UserModel.id == TenantInviteModel.invited_by)
            .where(TenantInviteModel.id == invite_id)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            return None

        model, inviter_name = row[0], row[1]
        names = await self._load_class_names(model.subject_class_ids)
        return TenantInviteMapper.to_domain(model, inviter_name, subject_class_names=names)

    async def find_by_token(self, token: str) -> TenantInvite | None:
        stmt = (
            select(TenantInviteModel, UserModel.name)
            .outerjoin(UserModel, UserModel.id == TenantInviteModel.invited_by)
            .where(TenantInviteModel.token == token)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            return None

        model, inviter_name = row[0], row[1]
        names = await self._load_class_names(model.subject_class_ids)
        return TenantInviteMapper.to_domain(model, inviter_name, subject_class_names=names)

    async def _load_class_names(self, raw_ids: list[str] | list[UUID] | None) -> list[str]:
        if not raw_ids:
            return []
        class_ids: list[UUID] = []
        for cid in raw_ids:
            try:
                class_ids.append(UUID(str(cid)))
            except (ValueError, TypeError):
                pass
        if not class_ids:
            return []
        stmt = select(SubjectClassModel.id, SubjectClassModel.name).where(
            SubjectClassModel.id.in_(class_ids)
        )
        res = await self.session.execute(stmt)
        name_map = {r[0]: r[1] for r in res.all()}
        return [name_map[cid] for cid in class_ids if cid in name_map]

    async def find_by_email_and_tenant(self, email: str, tenant_id: UUID) -> TenantInvite | None:
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
        sort_by: str = "created_at",
        order: str = "desc",
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
                conditions.extend(
                    [
                        TenantInviteModel.accepted_at.is_(None),
                        TenantInviteModel.revoked_at.is_(None),
                        TenantInviteModel.expires_at > now_expr,
                    ]
                )
            elif st == "accepted":
                conditions.append(TenantInviteModel.accepted_at.is_not(None))
            elif st == "revoked":
                conditions.append(TenantInviteModel.revoked_at.is_not(None))
            elif st == "expired":
                conditions.extend(
                    [
                        TenantInviteModel.accepted_at.is_(None),
                        TenantInviteModel.revoked_at.is_(None),
                        TenantInviteModel.expires_at <= now_expr,
                    ]
                )

        count_stmt = select(func.count(TenantInviteModel.id)).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one() or 0

        # Ordenação dinâmica
        sort_col = TenantInviteModel.created_at
        if sort_by == "email":
            sort_col = TenantInviteModel.email
        elif sort_by == "role":
            sort_col = TenantInviteModel.role
        elif sort_by == "expires_at":
            sort_col = TenantInviteModel.expires_at

        order_expr = sort_col.asc() if order.lower() == "asc" else sort_col.desc()

        items_stmt = (
            select(TenantInviteModel, UserModel.name)
            .outerjoin(UserModel, UserModel.id == TenantInviteModel.invited_by)
            .where(*conditions)
            .order_by(order_expr)
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )

        result = await self.session.execute(items_stmt)
        rows = result.all()

        # Resolução em lote dos nomes das turmas (zero N+1)
        all_class_ids: set[UUID] = set()
        for row in rows:
            if row[0].subject_class_ids:
                for cid in row[0].subject_class_ids:
                    try:
                        all_class_ids.add(UUID(str(cid)))
                    except (ValueError, TypeError):
                        pass

        class_names_map: dict[UUID, str] = {}
        if all_class_ids:
            class_stmt = select(SubjectClassModel.id, SubjectClassModel.name).where(
                SubjectClassModel.id.in_(all_class_ids)
            )
            class_res = await self.session.execute(class_stmt)
            class_names_map = {r[0]: r[1] for r in class_res.all()}

        items = []
        for row in rows:
            model = row[0]
            inviter_name = row[1]
            names: list[str] = []
            if model.subject_class_ids:
                for cid in model.subject_class_ids:
                    try:
                        uid = UUID(str(cid))
                        if uid in class_names_map:
                            names.append(class_names_map[uid])
                    except (ValueError, TypeError):
                        pass
            items.append(
                TenantInviteMapper.to_domain(
                    model=model,
                    invited_by_name=inviter_name,
                    subject_class_names=names,
                )
            )

        return Page.from_params(items, total=total, pagination=pagination)

    async def get_metrics(self, tenant_id: UUID, days: int = 30) -> TenantInvitesMetrics:
        conditions = [TenantInviteModel.tenant_id == tenant_id]

        if days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            conditions.append(TenantInviteModel.created_at >= cutoff)

        now_expr = func.now()

        stmt = select(
            func.count(TenantInviteModel.id).label("total"),
            func.count(
                case(
                    (
                        and_(
                            TenantInviteModel.accepted_at.is_(None),
                            TenantInviteModel.revoked_at.is_(None),
                            TenantInviteModel.expires_at > now_expr,
                        ),
                        1,
                    )
                )
            ).label("pending"),
            func.count(
                case(
                    (TenantInviteModel.accepted_at.is_not(None), 1),
                )
            ).label("accepted"),
            func.count(
                case(
                    (
                        and_(
                            TenantInviteModel.accepted_at.is_(None),
                            TenantInviteModel.revoked_at.is_(None),
                            TenantInviteModel.expires_at <= now_expr,
                        ),
                        1,
                    )
                )
            ).label("expired"),
            func.count(
                case(
                    (TenantInviteModel.revoked_at.is_not(None), 1),
                )
            ).label("revoked"),
        ).where(*conditions)

        row = (await self.session.execute(stmt)).one()
        total = row.total or 0
        pending = row.pending or 0
        accepted = row.accepted or 0
        expired = row.expired or 0
        revoked = row.revoked or 0

        resolved = accepted + expired + revoked
        acceptance_rate = round((accepted / resolved) * 100, 1) if resolved > 0 else 0.0

        return TenantInvitesMetrics(
            total=total,
            pending=pending,
            accepted=accepted,
            expired=expired,
            revoked=revoked,
            acceptance_rate=acceptance_rate,
            days=days,
        )

    async def save(self, invite: TenantInvite) -> TenantInvite:
        model = TenantInviteMapper.to_model(invite)
        merged = await self.session.merge(model)
        await self.session.flush()
        await self.session.refresh(merged)
        names = invite.subject_class_names
        if not names and model.subject_class_ids:
            names = await self._load_class_names(model.subject_class_ids)
        return TenantInviteMapper.to_domain(
            merged,
            invited_by_name=invite.invited_by_name,
            subject_class_names=names,
        )
