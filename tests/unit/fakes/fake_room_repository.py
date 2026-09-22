from uuid import UUID

from modules.room.domain.entities.room import Room


class FakeRoomRepository:

    def __init__(self) -> None:
        self._rooms: dict[UUID, Room] = {}

    async def save(self, room: Room) -> Room:
        self._rooms[room.id] = room
        return room

    async def find_by_id(
        self, room_id: UUID, include_deleted: bool = False
    ) -> Room | None:
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

    async def list_by_tenant(
        self, tenant_id: UUID, include_deleted: bool = False
    ) -> list[Room]:
        return [
            r for r in self._rooms.values()
            if r.tenant_id == tenant_id and (include_deleted or not r.deleted)
        ]

    async def delete(self, room: Room) -> None:
        room.deleted = True
        await self.save(room)
