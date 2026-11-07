from dataclasses import dataclass, field
from uuid import UUID

from modules.room.domain.entities.room import Room
from modules.room.domain.repositories.room_repository import RoomRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException
from shared.pagination import Page, PaginationParams


@dataclass
class ListRoomsInput:
    tenant_id: UUID
    pagination: PaginationParams = field(default_factory=PaginationParams)
    search: str | None = None


class ListRoomsUseCase:
    def __init__(
        self,
        room_repo: RoomRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.room_repo = room_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: ListRoomsInput) -> Page[Room]:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        return await self.room_repo.list_by_tenant_paginated(
            tenant_id=data.tenant_id,
            pagination=data.pagination,
            search=data.search,
        )
