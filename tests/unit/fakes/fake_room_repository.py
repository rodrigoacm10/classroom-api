from uuid import UUID

from modules.room.domain.entities.room import Room
from modules.room.domain.entities.room_metrics import RoomMetrics
from shared.pagination import Page, PaginationParams


class FakeRoomRepository:
    def __init__(self) -> None:
        self._rooms: dict[UUID, Room] = {}

    async def save(self, room: Room) -> Room:
        self._rooms[room.id] = room
        return room

    async def find_by_id(self, room_id: UUID, include_deleted: bool = False) -> Room | None:
        room = self._rooms.get(room_id)
        if room and (include_deleted or not room.deleted):
            return room
        return None

    async def find_by_id_and_tenant(
        self, room_id: UUID, tenant_id: UUID, include_deleted: bool = False
    ) -> Room | None:
        room = self._rooms.get(room_id)
        if room and room.tenant_id == tenant_id and (include_deleted or not room.deleted):
            return room
        return None

    async def list_by_tenant(self, tenant_id: UUID, include_deleted: bool = False) -> list[Room]:
        filtered = [
            r
            for r in self._rooms.values()
            if r.tenant_id == tenant_id and (include_deleted or not r.deleted)
        ]
        return sorted(filtered, key=lambda r: r.name)

    async def list_by_tenant_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> Page[Room]:
        items = [
            r
            for r in self._rooms.values()
            if r.tenant_id == tenant_id and (include_deleted or not r.deleted)
        ]
        if search and search.strip():
            term = search.strip().lower()
            items = [r for r in items if term in r.name.lower()]

        items = sorted(items, key=lambda r: r.name)
        total = len(items)
        sliced = items[pagination.offset : pagination.offset + pagination.page_size]
        return Page.from_params(items=sliced, total=total, pagination=pagination)

    async def get_metrics_by_tenant(self, tenant_id: UUID) -> RoomMetrics:
        rooms = [r for r in self._rooms.values() if r.tenant_id == tenant_id and not r.deleted]
        total_rooms = len(rooms)
        avg_radius = (
            round(sum(r.tolerance_radius_meters for r in rooms) / total_rooms)
            if total_rooms > 0
            else 0
        )
        precisas_count = sum(1 for r in rooms if r.tolerance_radius_meters <= 30)
        amplas_count = sum(1 for r in rooms if r.tolerance_radius_meters > 75)
        return RoomMetrics(
            total_rooms=total_rooms,
            avg_radius=avg_radius,
            precisas_count=precisas_count,
            amplas_count=amplas_count,
        )

    async def delete(self, room: Room) -> None:
        room.deleted = True
        await self.save(room)
