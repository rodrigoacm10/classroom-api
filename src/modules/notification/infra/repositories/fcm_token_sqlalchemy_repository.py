from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.user_fcm_token import UserFCMTokenModel
from modules.notification.domain.entities.fcm_token import FCMToken
from modules.notification.domain.repositories.fcm_token_repository import FCMTokenRepository
from modules.notification.infra.mappers.fcm_token_mapper import FCMTokenMapper


class FCMTokenSQLAlchemyRepository(FCMTokenRepository):

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, token: FCMToken) -> FCMToken:
        now = datetime.now(timezone.utc)
        stmt = (
            insert(UserFCMTokenModel)
            .values(
                id=token.id,
                user_id=token.user_id,
                device_id=token.device_id,
                fcm_token=token.fcm_token,
                platform=token.platform,
                app_version=token.app_version,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "device_id"],
                set_={
                    "fcm_token": token.fcm_token,
                    "platform": token.platform,
                    "app_version": token.app_version,
                    "updated_at": now,
                },
            )
            .returning(UserFCMTokenModel)
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one()
        await self.session.flush()
        return FCMTokenMapper.to_domain(model)

    async def find_by_user_and_device(
        self, user_id: UUID, device_id: str
    ) -> FCMToken | None:
        stmt = select(UserFCMTokenModel).where(
            UserFCMTokenModel.user_id == user_id,
            UserFCMTokenModel.device_id == device_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        return FCMTokenMapper.to_domain(model)

    async def remove(self, user_id: UUID, device_id: str) -> bool:
        stmt = (
            delete(UserFCMTokenModel)
            .where(
                UserFCMTokenModel.user_id == user_id,
                UserFCMTokenModel.device_id == device_id,
            )
            .returning(UserFCMTokenModel.id)
        )
        result = await self.session.execute(stmt)
        deleted_id = result.scalar_one_or_none()
        await self.session.flush()
        return deleted_id is not None

    async def remove_by_tokens(self, fcm_tokens: list[str]) -> int:
        if not fcm_tokens:
            return 0
        stmt = delete(UserFCMTokenModel).where(UserFCMTokenModel.fcm_token.in_(fcm_tokens))
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(getattr(result, "rowcount", 0))

    async def remove_by_user(self, user_id: UUID) -> int:
        stmt = delete(UserFCMTokenModel).where(UserFCMTokenModel.user_id == user_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(getattr(result, "rowcount", 0))


