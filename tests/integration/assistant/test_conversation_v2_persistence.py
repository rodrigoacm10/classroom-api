from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from modules.assistant.domain.entities.chat_conversation import ChatConversation
from modules.assistant.domain.entities.chat_message import ChatMessage
from modules.assistant.infra.repositories.conversation_sqlalchemy_repository import (
    ConversationSQLAlchemyRepository,
)
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


class TestConversationV2Persistence:
    async def test_count_messages_slice_and_summary_persistence(
        self, session: AsyncSession
    ) -> None:
        tenant = await TenantFactory.create(session)
        user = await UserFactory.create(session)
        repo = ConversationSQLAlchemyRepository(session=session)

        conv = await repo.create(
            ChatConversation(
                id=uuid4(),
                tenant_id=tenant.id,
                user_id=user.id,
                title="Conversa longa",
            )
        )
        assert conv.summary is None
        assert conv.summary_message_count == 0
        assert await repo.count_messages(conversation_id=conv.id) == 0

        base_time = datetime.now(UTC) - timedelta(minutes=20)
        for idx in range(10):
            await repo.add_message(
                ChatMessage(
                    id=uuid4(),
                    conversation_id=conv.id,
                    role="user" if idx % 2 == 0 else "assistant",
                    content=f"Turno {idx + 1}",
                    created_at=base_time + timedelta(seconds=idx),
                )
            )

        assert await repo.count_messages(conversation_id=conv.id) == 10

        first_slice = await repo.get_messages_slice(conversation_id=conv.id, offset=0, limit=4)
        assert [m.content for m in first_slice] == ["Turno 1", "Turno 2", "Turno 3", "Turno 4"]

        second_slice = await repo.get_messages_slice(conversation_id=conv.id, offset=4, limit=3)
        assert [m.content for m in second_slice] == ["Turno 5", "Turno 6", "Turno 7"]

        assert await repo.get_messages_slice(conversation_id=conv.id, offset=0, limit=0) == []

        await repo.update_summary(
            conversation_id=conv.id,
            summary="Usuário perguntou sobre a turma de Física e chamadas abertas.",
            summary_message_count=6,
        )

        reloaded = await repo.get_by_id(
            conversation_id=conv.id,
            tenant_id=tenant.id,
            user_id=user.id,
            include_messages=False,
        )
        assert reloaded is not None
        assert reloaded.summary == "Usuário perguntou sobre a turma de Física e chamadas abertas."
        assert reloaded.summary_message_count == 6

    async def test_message_feedback_persistence_toggle_and_ownership_isolation(
        self, session: AsyncSession
    ) -> None:
        tenant_a = await TenantFactory.create(session)
        tenant_b = await TenantFactory.create(session)
        owner = await UserFactory.create(session)
        other_user = await UserFactory.create(session)
        repo = ConversationSQLAlchemyRepository(session=session)

        conv = await repo.create(
            ChatConversation(
                id=uuid4(),
                tenant_id=tenant_a.id,
                user_id=owner.id,
                title="Feedback test",
            )
        )
        assistant_msg = await repo.add_message(
            ChatMessage(
                id=uuid4(),
                conversation_id=conv.id,
                role="assistant",
                content="Há 2 chamadas abertas agora.",
            )
        )
        assert assistant_msg.feedback_rating is None
        assert assistant_msg.feedback_comment is None
        assert assistant_msg.feedback_updated_at is None

        # Cross-user and cross-tenant isolation
        assert (
            await repo.get_message_by_id(
                conversation_id=conv.id,
                message_id=assistant_msg.id,
                tenant_id=tenant_a.id,
                user_id=other_user.id,
            )
            is None
        )
        assert (
            await repo.set_message_feedback(
                conversation_id=conv.id,
                message_id=assistant_msg.id,
                tenant_id=tenant_a.id,
                user_id=other_user.id,
                rating="up",
            )
            is None
        )
        assert (
            await repo.set_message_feedback(
                conversation_id=conv.id,
                message_id=assistant_msg.id,
                tenant_id=tenant_b.id,
                user_id=owner.id,
                rating="up",
            )
            is None
        )

        # Owner sets thumbs up
        rated_up = await repo.set_message_feedback(
            conversation_id=conv.id,
            message_id=assistant_msg.id,
            tenant_id=tenant_a.id,
            user_id=owner.id,
            rating="up",
        )
        assert rated_up is not None
        assert rated_up.feedback_rating == "up"
        assert rated_up.feedback_comment is None
        assert rated_up.feedback_updated_at is not None

        # Owner switches to thumbs down with comment
        rated_down = await repo.set_message_feedback(
            conversation_id=conv.id,
            message_id=assistant_msg.id,
            tenant_id=tenant_a.id,
            user_id=owner.id,
            rating="down",
            comment="Faltou o link da sala",
        )
        assert rated_down is not None
        assert rated_down.feedback_rating == "down"
        assert rated_down.feedback_comment == "Faltou o link da sala"
        assert rated_down.feedback_updated_at is not None

        # Reload via get_by_id preserves feedback fields
        loaded_conv = await repo.get_by_id(
            conversation_id=conv.id,
            tenant_id=tenant_a.id,
            user_id=owner.id,
            include_messages=True,
        )
        assert loaded_conv is not None
        assert len(loaded_conv.messages) == 1
        assert loaded_conv.messages[0].feedback_rating == "down"
        assert loaded_conv.messages[0].feedback_comment == "Faltou o link da sala"

        # Owner clears feedback (toggle off)
        cleared = await repo.set_message_feedback(
            conversation_id=conv.id,
            message_id=assistant_msg.id,
            tenant_id=tenant_a.id,
            user_id=owner.id,
            rating=None,
        )
        assert cleared is not None
        assert cleared.feedback_rating is None
        assert cleared.feedback_comment is None
        assert cleared.feedback_updated_at is None

