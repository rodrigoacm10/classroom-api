from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.room import RoomModel
from modules.room.domain.entities.room import Room
from modules.room.domain.entities.room_metrics import RoomMetrics
from modules.room.infra.mappers.room_mapper import RoomMapper
from shared.pagination import Page, PaginationParams


class RoomSQLAlchemyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, room: Room) -> Room:
        model = RoomMapper.to_model(room)
        merged = await self.session.merge(model)
        await self.session.flush()
        await self.session.refresh(merged)
        return RoomMapper.to_domain(merged)

    async def find_by_id(self, room_id: UUID, include_deleted: bool = False) -> Room | None:
        stmt = select(RoomModel).where(RoomModel.id == room_id)
        if not include_deleted:
            stmt = stmt.where(RoomModel.deleted == False)  # noqa: E712
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return RoomMapper.to_domain(model) if model else None

    async def find_by_id_and_tenant(
        self, room_id: UUID, tenant_id: UUID, include_deleted: bool = False
    ) -> Room | None:
        stmt = select(RoomModel).where(
            RoomModel.id == room_id,
            RoomModel.tenant_id == tenant_id,
        )
        if not include_deleted:
            stmt = stmt.where(RoomModel.deleted == False)  # noqa: E712
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return RoomMapper.to_domain(model) if model else None

    async def list_by_tenant(self, tenant_id: UUID, include_deleted: bool = False) -> list[Room]:
        stmt = select(RoomModel).where(RoomModel.tenant_id == tenant_id)
        if not include_deleted:
            stmt = stmt.where(RoomModel.deleted == False)  # noqa: E712
        stmt = stmt.order_by(RoomModel.name.asc())
        result = await self.session.execute(stmt)
        return [RoomMapper.to_domain(m) for m in result.scalars().all()]

    async def list_by_tenant_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> Page[Room]:
        conditions = [RoomModel.tenant_id == tenant_id]
        if not include_deleted:
            conditions.append(RoomModel.deleted == False)  # noqa: E712
        if search and search.strip():
            conditions.append(RoomModel.name.ilike(f"%{search.strip()}%"))

        count_stmt = select(func.count(RoomModel.id)).where(*conditions)
        total_result = await self.session.execute(count_stmt)
        total = int(total_result.scalar_one() or 0)

        stmt = (
            select(RoomModel)
            .where(*conditions)
            .order_by(RoomModel.name.asc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
        result = await self.session.execute(stmt)
        rooms = [RoomMapper.to_domain(m) for m in result.scalars().all()]

        return Page.from_params(items=rooms, total=total, pagination=pagination)

    async def get_metrics_by_tenant(self, tenant_id: UUID) -> RoomMetrics:
        stmt = select(
            func.count(RoomModel.id),
            func.coalesce(func.avg(RoomModel.tolerance_radius_meters), 0),
            func.coalesce(func.sum(case((RoomModel.tolerance_radius_meters <= 30, 1), else_=0)), 0),
            func.coalesce(func.sum(case((RoomModel.tolerance_radius_meters > 75, 1), else_=0)), 0),
        ).where(
            RoomModel.tenant_id == tenant_id,
            RoomModel.deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        row = result.one()
        total_rooms = int(row[0] or 0)
        avg_radius = round(float(row[1] or 0))
        precisas_count = int(row[2] or 0)
        amplas_count = int(row[3] or 0)

        return RoomMetrics(
            total_rooms=total_rooms,
            avg_radius=avg_radius,
            precisas_count=precisas_count,
            amplas_count=amplas_count,
        )

    async def delete(self, room: Room) -> None:
        room.deleted = True
        await self.save(room)
