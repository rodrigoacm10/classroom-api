from dataclasses import dataclass
from uuid import UUID

from modules.room.domain.repositories.room_repository import RoomRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class DeleteRoomInput:
    room_id: UUID
    tenant_id: UUID


class DeleteRoomUseCase:

    def __init__(self, room_repo: RoomRepository) -> None:
        self.room_repo = room_repo

    async def execute(self, data: DeleteRoomInput) -> None:
        room = await self.room_repo.find_by_id_and_tenant(
            room_id=data.room_id,
            tenant_id=data.tenant_id,
        )
        if not room:
            raise ResourceNotFoundException("Sala não encontrada.")

        await self.room_repo.delete(room)
