from dataclasses import dataclass
from uuid import UUID

from modules.room.domain.entities.room import Room
from modules.room.domain.repositories.room_repository import RoomRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class ListRoomsInput:
    tenant_id: UUID


class ListRoomsUseCase:

    def __init__(
        self,
        room_repo: RoomRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.room_repo = room_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: ListRoomsInput) -> list[Room]:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        return await self.room_repo.list_by_tenant(data.tenant_id)
