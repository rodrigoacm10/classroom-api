from dataclasses import dataclass
from uuid import UUID

from modules.room.domain.entities.room import Room
from modules.room.domain.repositories.room_repository import RoomRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class CreateRoomInput:
    tenant_id: UUID
    name: str
    latitude: float
    longitude: float
    tolerance_radius_meters: int = 50
    created_by: UUID | None = None


class CreateRoomUseCase:

    def __init__(
        self,
        room_repo: RoomRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.room_repo = room_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: CreateRoomInput) -> Room:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        room = Room(
            tenant_id=data.tenant_id,
            name=data.name,
            latitude=data.latitude,
            longitude=data.longitude,
            tolerance_radius_meters=data.tolerance_radius_meters,
            created_by=data.created_by,
        )

        return await self.room_repo.save(room)
