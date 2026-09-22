from infra.database.models.user import UserModel
from modules.user.domain.entities.user import User


class UserMapper:

    @staticmethod
    def to_domain(model: UserModel) -> User:
        return User(
            id=model.id,
            name=model.name,
            email=model.email,
            password_hash=model.password_hash,
            fcm_token=model.fcm_token,
            created_at=model.created_at,
        )

    @staticmethod
    def to_model(entity: User) -> UserModel:
        return UserModel(
            id=entity.id,
            name=entity.name,
            email=entity.email,
            password_hash=entity.password_hash,
            fcm_token=entity.fcm_token,
        )
