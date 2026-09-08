from typing import Protocol
from uuid import UUID

from modules.notification.domain.entities.fcm_token import FCMToken


class FCMTokenRepository(Protocol):

    async def upsert(self, token: FCMToken) -> FCMToken: ...

    async def find_by_user_and_device(self, user_id: UUID, device_id: str) -> FCMToken | None: ...

    async def remove(self, user_id: UUID, device_id: str) -> bool: ...
