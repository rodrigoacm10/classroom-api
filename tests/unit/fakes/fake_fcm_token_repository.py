from uuid import UUID

from modules.notification.domain.entities.fcm_token import FCMToken
from modules.notification.domain.repositories.fcm_token_repository import FCMTokenRepository


class FakeFCMTokenRepository(FCMTokenRepository):

    def __init__(self) -> None:
        self.tokens: list[FCMToken] = []

    async def upsert(self, token: FCMToken) -> FCMToken:
        existing = await self.find_by_user_and_device(token.user_id, token.device_id)
        if existing:
            existing.fcm_token = token.fcm_token
            existing.platform = token.platform
            existing.app_version = token.app_version
            existing.updated_at = token.updated_at
            return existing
        self.tokens.append(token)
        return token

    async def find_by_user_and_device(self, user_id: UUID, device_id: str) -> FCMToken | None:
        for t in self.tokens:
            if t.user_id == user_id and t.device_id == device_id:
                return t
        return None

    async def remove(self, user_id: UUID, device_id: str) -> bool:
        token = await self.find_by_user_and_device(user_id, device_id)
        if token:
            self.tokens.remove(token)
            return True
        return False

    async def remove_by_tokens(self, fcm_tokens: list[str]) -> int:
        initial_count = len(self.tokens)
        self.tokens = [t for t in self.tokens if t.fcm_token not in fcm_tokens]
        return initial_count - len(self.tokens)

    async def remove_by_user(self, user_id: UUID) -> int:
        initial_count = len(self.tokens)
        self.tokens = [t for t in self.tokens if t.user_id != user_id]
        return initial_count - len(self.tokens)

