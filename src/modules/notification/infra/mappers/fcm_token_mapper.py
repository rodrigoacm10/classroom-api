from infra.database.models.user_fcm_token import UserFCMTokenModel
from modules.notification.domain.entities.fcm_token import FCMToken


class FCMTokenMapper:

    @staticmethod
    def to_domain(model: UserFCMTokenModel) -> FCMToken:
        return FCMToken(
            id=model.id,
            user_id=model.user_id,
            device_id=model.device_id,
            fcm_token=model.fcm_token,
            platform=model.platform,
            app_version=model.app_version,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_persistence(entity: FCMToken) -> UserFCMTokenModel:
        return UserFCMTokenModel(
            id=entity.id,
            user_id=entity.user_id,
            device_id=entity.device_id,
            fcm_token=entity.fcm_token,
            platform=entity.platform,
            app_version=entity.app_version,
            updated_at=entity.updated_at,
        )
