from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.user import UserModel
from modules.user.domain.entities.user import User
from modules.user.infra.mappers.user_mapper import UserMapper


class UserSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_id(self, user_id: UUID) -> User | None:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return UserMapper.to_domain(model) if model else None

    async def find_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return UserMapper.to_domain(model) if model else None

    async def save(self, user: User) -> User:
        model = UserMapper.to_model(user)
        merged_model = await self.session.merge(model)
        await self.session.commit()
        await self.session.refresh(merged_model)
        return UserMapper.to_domain(merged_model)
