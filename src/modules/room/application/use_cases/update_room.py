from dataclasses import dataclass
from uuid import UUID

from modules.room.domain.entities.room import Room
from modules.room.domain.repositories.room_repository import RoomRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class UpdateRoomInput:
    room_id: UUID
    tenant_id: UUID
    name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    tolerance_radius_meters: int | None = None


class UpdateRoomUseCase:

    def __init__(self, room_repo: RoomRepository) -> None:
        self.room_repo = room_repo

    async def execute(self, data: UpdateRoomInput) -> Room:
        room = await self.room_repo.find_by_id_and_tenant(
            room_id=data.room_id,
            tenant_id=data.tenant_id,
        )
        if not room:
            raise ResourceNotFoundException("Sala não encontrada.")

        if data.name is not None:
            room.name = data.name
        if data.latitude is not None:
            room.latitude = data.latitude
        if data.longitude is not None:
            room.longitude = data.longitude
        if data.tolerance_radius_meters is not None:
            room.tolerance_radius_meters = data.tolerance_radius_meters

        return await self.room_repo.save(room)
