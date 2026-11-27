from uuid import uuid4

import pytest

from modules.assistant.application.use_cases.conversation.submit_message_feedback import (
    SubmitMessageFeedbackInput,
    SubmitMessageFeedbackUseCase,
)
from modules.assistant.domain.entities.chat_conversation import ChatConversation
from modules.assistant.domain.entities.chat_message import ChatMessage
from shared.exceptions import BusinessRuleException, ResourceNotFoundException
from tests.unit.assistant.test_send_message import FakeConversationRepository


class TestSubmitMessageFeedbackUseCase:
    async def test_sets_switches_and_clears_feedback_on_assistant_message(self) -> None:
        tenant_id = uuid4()
        user_id = uuid4()
        conv_id = uuid4()
        msg_id = uuid4()

        repo = FakeConversationRepository()
        await repo.create(
            ChatConversation(id=conv_id, tenant_id=tenant_id, user_id=user_id, title="Teste")
        )
        await repo.add_message(
            ChatMessage(
                id=msg_id,
                conversation_id=conv_id,
                role="assistant",
                content="Há 1 chamada aberta agora.",
            )
        )
        use_case = SubmitMessageFeedbackUseCase(conversation_repo=repo)

        up = await use_case.execute(
            SubmitMessageFeedbackInput(
                conversation_id=conv_id,
                message_id=msg_id,
                tenant_id=tenant_id,
                user_id=user_id,
                rating="up",
            )
        )
        assert up.feedback_rating == "up"
        assert up.feedback_comment is None
        assert up.feedback_updated_at is not None

        down = await use_case.execute(
            SubmitMessageFeedbackInput(
                conversation_id=conv_id,
                message_id=msg_id,
                tenant_id=tenant_id,
                user_id=user_id,
                rating="down",
                comment="  Resposta incompleta  ",
            )
        )
        assert down.feedback_rating == "down"
        assert down.feedback_comment == "Resposta incompleta"

        cleared = await use_case.execute(
            SubmitMessageFeedbackInput(
                conversation_id=conv_id,
                message_id=msg_id,
                tenant_id=tenant_id,
                user_id=user_id,
                rating=None,
            )
        )
        assert cleared.feedback_rating is None
        assert cleared.feedback_comment is None
        assert cleared.feedback_updated_at is None

    async def test_rejects_user_role_message_and_enforces_ownership(self) -> None:
        tenant_id = uuid4()
        owner_id = uuid4()
        other_user_id = uuid4()
        conv_id = uuid4()
        user_msg_id = uuid4()
        assistant_msg_id = uuid4()

        repo = FakeConversationRepository()
        await repo.create(
            ChatConversation(id=conv_id, tenant_id=tenant_id, user_id=owner_id, title="Teste")
        )
        await repo.add_message(
            ChatMessage(
                id=user_msg_id,
                conversation_id=conv_id,
                role="user",
                content="Tem chamada aberta?",
            )
        )
        await repo.add_message(
            ChatMessage(
                id=assistant_msg_id,
                conversation_id=conv_id,
                role="assistant",
                content="Sim, 1 chamada.",
            )
        )
        use_case = SubmitMessageFeedbackUseCase(conversation_repo=repo)

        with pytest.raises(BusinessRuleException, match="assistente"):
            await use_case.execute(
                SubmitMessageFeedbackInput(
                    conversation_id=conv_id,
                    message_id=user_msg_id,
                    tenant_id=tenant_id,
                    user_id=owner_id,
                    rating="up",
                )
            )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                SubmitMessageFeedbackInput(
                    conversation_id=conv_id,
                    message_id=assistant_msg_id,
                    tenant_id=tenant_id,
                    user_id=other_user_id,
                    rating="up",
                )
            )

