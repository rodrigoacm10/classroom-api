import pytest

from modules.notification.domain.entities.fcm_token import FCMToken
from modules.notification.infra.repositories.fcm_token_sqlalchemy_repository import (
    FCMTokenSQLAlchemyRepository,
)
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestFCMTokenSQLAlchemyRepository:
    """
    Suíte de Testes (Integração): FCMTokenSQLAlchemyRepository
    Valida a execução de queries no PostgreSQL para o gerenciamento de tokens FCM.
    """

    async def test_remove_by_tokens_deletes_specified_fcm_tokens_from_db(self, session):
        """Deve remover do banco de dados exatamente os tokens FCM cujas strings foram especificadas."""
        user = await UserFactory.create(session)
        repo = FCMTokenSQLAlchemyRepository(session)

        # Cadastrar 3 tokens para o usuário
        await repo.upsert(
            FCMToken(
                user_id=user.id,
                device_id="dev_1",
                fcm_token="token_alpha_1",
                platform="android",
            )
        )
        await repo.upsert(
            FCMToken(
                user_id=user.id,
                device_id="dev_2",
                fcm_token="token_beta_2",
                platform="ios",
            )
        )
        await repo.upsert(
            FCMToken(
                user_id=user.id,
                device_id="dev_3",
                fcm_token="token_gamma_3",
                platform="android",
            )
        )

        # Remover apenas 2 dos 3 tokens
        removed_count = await repo.remove_by_tokens(["token_alpha_1", "token_beta_2"])
        assert removed_count == 2

        # Verificar se apenas o terceiro token restou no banco
        token_1 = await repo.find_by_user_and_device(user.id, "dev_1")
        token_2 = await repo.find_by_user_and_device(user.id, "dev_2")
        token_3 = await repo.find_by_user_and_device(user.id, "dev_3")

        assert token_1 is None
        assert token_2 is None
        assert token_3 is not None
        assert token_3.fcm_token == "token_gamma_3"

    async def test_remove_by_user_deletes_all_tokens_for_given_user_id(self, session):
        """Deve remover todos os tokens FCM vinculados a um determinado usuário no PostgreSQL."""
        user_a = await UserFactory.create(session)
        user_b = await UserFactory.create(session)
        repo = FCMTokenSQLAlchemyRepository(session)

        # Tokens para user_a
        await repo.upsert(
            FCMToken(
                user_id=user_a.id,
                device_id="dev_a1",
                fcm_token="token_user_a1",
                platform="android",
            )
        )
        await repo.upsert(
            FCMToken(
                user_id=user_a.id,
                device_id="dev_a2",
                fcm_token="token_user_a2",
                platform="ios",
            )
        )

        # Token para user_b
        await repo.upsert(
            FCMToken(
                user_id=user_b.id,
                device_id="dev_b1",
                fcm_token="token_user_b1",
                platform="android",
            )
        )

        # Deletar todos do user_a
        removed_count = await repo.remove_by_user(user_a.id)
        assert removed_count == 2

        # Verificar que user_a não tem mais tokens e user_b continua intacto
        assert await repo.find_by_user_and_device(user_a.id, "dev_a1") is None
        assert await repo.find_by_user_and_device(user_a.id, "dev_a2") is None

        user_b_token = await repo.find_by_user_and_device(user_b.id, "dev_b1")
        assert user_b_token is not None
        assert user_b_token.fcm_token == "token_user_b1"
