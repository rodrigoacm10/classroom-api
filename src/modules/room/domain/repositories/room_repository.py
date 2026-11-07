from typing import Protocol
from uuid import UUID

from modules.room.domain.entities.room import Room
from modules.room.domain.entities.room_metrics import RoomMetrics
from shared.pagination import Page, PaginationParams


class RoomRepository(Protocol):
    async def save(self, room: Room) -> Room: ...

    async def find_by_id(self, room_id: UUID, include_deleted: bool = False) -> Room | None: ...

    async def find_by_id_and_tenant(
        self, room_id: UUID, tenant_id: UUID, include_deleted: bool = False
    ) -> Room | None: ...

    async def list_by_tenant(
        self, tenant_id: UUID, include_deleted: bool = False
    ) -> list[Room]: ...

    async def list_by_tenant_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> Page[Room]: ...

    async def get_metrics_by_tenant(self, tenant_id: UUID) -> RoomMetrics: ...

    async def delete(self, room: Room) -> None: ...
