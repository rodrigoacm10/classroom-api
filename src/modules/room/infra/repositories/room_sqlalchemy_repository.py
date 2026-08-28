from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.room import RoomModel
from modules.room.domain.entities.room import Room
from modules.room.infra.mappers.room_mapper import RoomMapper


class RoomSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, room: Room) -> Room:
        model = RoomMapper.to_model(room)
        merged = await self.session.merge(model)
        await self.session.commit()
        await self.session.refresh(merged)
        return RoomMapper.to_domain(merged)

    async def find_by_id(
        self, room_id: UUID, include_deleted: bool = False
    ) -> Room | None:
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

    async def list_by_tenant(
        self, tenant_id: UUID, include_deleted: bool = False
    ) -> list[Room]:
        stmt = select(RoomModel).where(RoomModel.tenant_id == tenant_id)
        if not include_deleted:
            stmt = stmt.where(RoomModel.deleted == False)  # noqa: E712
        result = await self.session.execute(stmt)
        return [RoomMapper.to_domain(m) for m in result.scalars().all()]

    async def delete(self, room: Room) -> None:
        room.deleted = True
        await self.save(room)
