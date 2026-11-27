from unittest.mock import AsyncMock
from uuid import uuid4

from modules.assistant.application.use_cases.conversation.send_message import (
    SendMessageInput,
    SendMessageUseCase,
)
from modules.assistant.application.use_cases.conversation.summarize_conversation import (
    SummarizeConversationInput,
    SummarizeConversationUseCase,
)
from modules.assistant.application.use_cases.knowledge.retrieve_knowledge import (
    RetrieveKnowledgeUseCase,
)
from modules.assistant.domain.entities.chat_conversation import ChatConversation
from modules.assistant.domain.entities.chat_message import ChatMessage
from modules.assistant.domain.entities.llm_events import LLMStreamEvent
from shared.enums.user_role import UserRole
from tests.unit.assistant.test_send_message import (
    FakeConversationRepository,
    FakeEmbeddingProvider,
    FakeKnowledgeRepository,
    FakeLLMProvider,
)


class TestSummarizeConversationUseCase:
    async def test_does_not_trigger_when_overflow_is_below_batch_threshold(self) -> None:
        conv_id = uuid4()
        conv_repo = FakeConversationRepository()
        await conv_repo.create(
            ChatConversation(id=conv_id, tenant_id=uuid4(), user_id=uuid4(), title="Curta")
        )

        # 13 messages = 5 outside window (8), below batch threshold (6)
        for idx in range(13):
            await conv_repo.add_message(
                ChatMessage(
                    id=uuid4(),
                    conversation_id=conv_id,
                    role="user" if idx % 2 == 0 else "assistant",
                    content=f"Msg {idx + 1}",
                )
            )

        llm = FakeLLMProvider(turns=[[LLMStreamEvent(kind="delta", text="Não deveria rodar")]])
        use_case = SummarizeConversationUseCase(
            conversation_repo=conv_repo,
            llm_provider=llm,
            history_window=8,
            batch_threshold=6,
        )

        result = await use_case.execute(
            SummarizeConversationInput(
                conversation_id=conv_id,
                existing_summary=None,
                summary_message_count=0,
            )
        )

        assert result is None
        assert llm.recorded_calls == []
        assert conv_repo.conversations[conv_id].summary is None
        assert conv_repo.conversations[conv_id].summary_message_count == 0

    async def test_triggers_at_threshold_and_incrementally_merges_subsequent_batches(
        self,
    ) -> None:
        conv_id = uuid4()
        conv_repo = FakeConversationRepository()
        await conv_repo.create(
            ChatConversation(id=conv_id, tenant_id=uuid4(), user_id=uuid4(), title="Longa")
        )

        # 14 messages -> 6 unsummarized messages outside window 8
        for idx in range(14):
            await conv_repo.add_message(
                ChatMessage(
                    id=uuid4(),
                    conversation_id=conv_id,
                    role="user" if idx % 2 == 0 else "assistant",
                    content=f"Turno {idx + 1}",
                )
            )

        llm = FakeLLMProvider(
            turns=[
                [LLMStreamEvent(kind="delta", text="Resumo inicial: turnos 1 a 6 sobre Física.")],
                [LLMStreamEvent(kind="delta", text="Resumo atualizado: turnos 1 a 12 sobre Física e Cálculo.")],
            ]
        )
        use_case = SummarizeConversationUseCase(
            conversation_repo=conv_repo,
            llm_provider=llm,
            history_window=8,
            batch_threshold=6,
        )

        first_summary = await use_case.execute(
            SummarizeConversationInput(
                conversation_id=conv_id,
                existing_summary=None,
                summary_message_count=0,
            )
        )

        assert first_summary == "Resumo inicial: turnos 1 a 6 sobre Física."
        assert conv_repo.conversations[conv_id].summary == first_summary
        assert conv_repo.conversations[conv_id].summary_message_count == 6
        assert llm.recorded_calls[0]["tools"] == []
        assert "Turno 1" in llm.recorded_calls[0]["messages"][0]["content"]
        assert "Turno 6" in llm.recorded_calls[0]["messages"][0]["content"]
        assert "Turno 7" not in llm.recorded_calls[0]["messages"][0]["content"]

        # Add 6 more messages (total 20) -> next batch of 6 (Turnos 7..12)
        for idx in range(14, 20):
            await conv_repo.add_message(
                ChatMessage(
                    id=uuid4(),
                    conversation_id=conv_id,
                    role="user" if idx % 2 == 0 else "assistant",
                    content=f"Turno {idx + 1}",
                )
            )

        second_summary = await use_case.execute(
            SummarizeConversationInput(
                conversation_id=conv_id,
                existing_summary=first_summary,
                summary_message_count=6,
            )
        )

        assert second_summary == "Resumo atualizado: turnos 1 a 12 sobre Física e Cálculo."
        assert conv_repo.conversations[conv_id].summary == second_summary
        assert conv_repo.conversations[conv_id].summary_message_count == 12
        second_prompt = llm.recorded_calls[1]["messages"][0]["content"]
        assert "Resumo anterior:" in second_prompt
        assert first_summary in second_prompt
        assert "Turno 7" in second_prompt
        assert "Turno 12" in second_prompt

    async def test_send_message_injects_existing_summary_and_swallows_summarizer_error(
        self,
    ) -> None:
        tenant_id = uuid4()
        user_id = uuid4()
        conv_id = uuid4()

        conv_repo = FakeConversationRepository()
        await conv_repo.create(
            ChatConversation(
                id=conv_id,
                tenant_id=tenant_id,
                user_id=user_id,
                title="Conversa com resumo",
                summary="Usuário estava analisando faltas da turma de Física I.",
                summary_message_count=6,
            )
        )

        retrieve_uc = RetrieveKnowledgeUseCase(
            knowledge_repo=FakeKnowledgeRepository(),
            embedding_provider=FakeEmbeddingProvider(),
        )
        llm = FakeLLMProvider(
            turns=[[LLMStreamEvent(kind="delta", text="Certo, continuando sobre Física I.")]]
        )
        failing_summarizer = AsyncMock()
        failing_summarizer.execute.side_effect = RuntimeError("LLM summary timeout")

        use_case = SendMessageUseCase(
            conversation_repo=conv_repo,
            retrieve_knowledge_use_case=retrieve_uc,
            llm_provider=llm,
            summarize_conversation_use_case=failing_summarizer,
        )

        stream = await use_case.execute(
            SendMessageInput(
                conversation_id=conv_id,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role=UserRole.PROFESSOR,
                content="E qual era a taxa média dela mesmo?",
            )
        )
        events = [ev async for ev in stream]

        assert [ev.event for ev in events] == ["delta", "done"]
        assert "## Resumo da conversa anterior" in llm.recorded_calls[0]["system_prompt"]
        assert "Física I" in llm.recorded_calls[0]["system_prompt"]
        failing_summarizer.execute.assert_awaited_once()

