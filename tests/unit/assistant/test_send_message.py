from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from modules.assistant.application.prompts import build_system_prompt
from modules.assistant.application.use_cases.conversation.send_message import (
    FALLBACK_MAX_ITERATIONS_TEXT,
    SendMessageInput,
    SendMessageUseCase,
)
from modules.assistant.application.use_cases.conversation.summarize_conversation import (
    SummarizeConversationUseCase,
)
from modules.assistant.application.use_cases.knowledge.retrieve_knowledge import (
    RetrieveKnowledgeUseCase,
)
from modules.assistant.domain.entities.chat_conversation import ChatConversation
from modules.assistant.domain.entities.chat_message import ChatMessage, FeedbackRating
from modules.assistant.domain.entities.knowledge_chunk import KnowledgeChunk, RetrievedChunk
from modules.assistant.domain.entities.llm_events import LLMStreamEvent, ToolCallRequest
from modules.assistant.infra.gemini.gemini_llm_provider import GeminiLLMProvider
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


class FakeEmbeddingProvider:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 4 for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [0.2] * 4


class FakeKnowledgeRepository:
    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self._chunks = chunks or []
        self.queries: list[tuple[str, UserRole]] = []

    async def get_existing_hashes(self, doc_slug: str) -> set[str]:
        return set()

    async def upsert_chunks(self, chunks: list[KnowledgeChunk]) -> int:
        return len(chunks)

    async def delete_chunks_not_in(self, doc_slug: str, valid_hashes: set[str]) -> int:
        return 0

    async def vector_search(
        self,
        *,
        query_embedding: list[float],
        user_role: UserRole,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        return list(self._chunks[:limit])

    async def full_text_search(
        self,
        *,
        query_text: str,
        user_role: UserRole,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        self.queries.append((query_text, user_role))
        return list(self._chunks[:limit])


class FakeConversationRepository:
    def __init__(self) -> None:
        self.conversations: dict[UUID, ChatConversation] = {}
        self.messages: list[ChatMessage] = []

    async def create(self, conversation: ChatConversation) -> ChatConversation:
        self.conversations[conversation.id] = conversation
        return conversation

    async def list_by_user(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ChatConversation]:
        items = [
            c
            for c in self.conversations.values()
            if c.tenant_id == tenant_id and c.user_id == user_id
        ]
        return items[offset : offset + limit]

    async def get_by_id(
        self,
        *,
        conversation_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        include_messages: bool = True,
    ) -> ChatConversation | None:
        conv = self.conversations.get(conversation_id)
        if conv is None or conv.tenant_id != tenant_id or conv.user_id != user_id:
            return None
        if include_messages:
            conv.messages = [m for m in self.messages if m.conversation_id == conversation_id]
        return conv

    async def update_title(self, *, conversation_id: UUID, title: str) -> None:
        if conversation_id in self.conversations:
            self.conversations[conversation_id].title = title

    async def delete(
        self,
        *,
        conversation_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
    ) -> bool:
        conv = self.conversations.get(conversation_id)
        if conv is None or conv.tenant_id != tenant_id or conv.user_id != user_id:
            return False
        del self.conversations[conversation_id]
        return True

    async def add_message(self, message: ChatMessage) -> ChatMessage:
        self.messages.append(message)
        return message

    async def get_recent_messages(
        self,
        *,
        conversation_id: UUID,
        limit: int = 8,
    ) -> list[ChatMessage]:
        conv_msgs = [m for m in self.messages if m.conversation_id == conversation_id]
        return conv_msgs[-limit:]

    async def count_messages(self, *, conversation_id: UUID) -> int:
        return sum(1 for m in self.messages if m.conversation_id == conversation_id)

    async def get_messages_slice(
        self,
        *,
        conversation_id: UUID,
        offset: int,
        limit: int,
    ) -> list[ChatMessage]:
        if limit <= 0:
            return []
        conv_msgs = [m for m in self.messages if m.conversation_id == conversation_id]
        return conv_msgs[offset : offset + limit]

    async def update_summary(
        self,
        *,
        conversation_id: UUID,
        summary: str,
        summary_message_count: int,
    ) -> None:
        if conversation_id in self.conversations:
            self.conversations[conversation_id].summary = summary
            self.conversations[conversation_id].summary_message_count = summary_message_count

    async def get_message_by_id(
        self,
        *,
        conversation_id: UUID,
        message_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
    ) -> ChatMessage | None:
        conv = self.conversations.get(conversation_id)
        if conv is None or conv.tenant_id != tenant_id or conv.user_id != user_id:
            return None
        return next(
            (
                m
                for m in self.messages
                if m.conversation_id == conversation_id and m.id == message_id
            ),
            None,
        )

    async def set_message_feedback(
        self,
        *,
        conversation_id: UUID,
        message_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        rating: FeedbackRating | None,
        comment: str | None = None,
    ) -> ChatMessage | None:
        msg = await self.get_message_by_id(
            conversation_id=conversation_id,
            message_id=message_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if msg is None:
            return None
        if rating is None:
            msg.feedback_rating = None
            msg.feedback_comment = None
            msg.feedback_updated_at = None
        else:
            msg.feedback_rating = rating
            msg.feedback_comment = comment
            msg.feedback_updated_at = datetime.now(UTC)
        return msg


class FakeLLMProvider:
    """Fake determinístico que reproduz uma sequência configurada de turnos de streaming."""

    def __init__(
        self,
        turns: list[list[LLMStreamEvent]],
        *,
        fail_with: Exception | None = None,
    ) -> None:
        self._turns = list(turns)
        self._fail_with = fail_with
        self.recorded_calls: list[dict[str, Any]] = []

    @property
    def model_name(self) -> str:
        return "fake-gemini-2.5-flash"

    async def stream_turn(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[LLMStreamEvent]:
        self.recorded_calls.append(
            {
                "system_prompt": system_prompt,
                "messages": [dict(m) for m in messages],
                "tools": list(tools),
            }
        )
        if self._fail_with is not None:
            raise self._fail_with

        events = self._turns.pop(0) if self._turns else []
        for event in events:
            yield event


class TestBuildSystemPrompt:
    def test_includes_user_role_route_and_professor_restrictions(self) -> None:
        prompt = build_system_prompt(
            user_role=UserRole.PROFESSOR,
            current_route="/dashboard/chamadas",
        )
        assert "Professor (professor)" in prompt
        assert "/dashboard/chamadas" in prompt
        assert "/dashboard/convites" in prompt
        assert "search_locus_docs" in prompt


class TestSendMessageUseCase:
    async def test_conversational_greeting_replies_directly_without_tool_call(self) -> None:
        tenant_id = uuid4()
        user_id = uuid4()
        conv_id = uuid4()

        conv_repo = FakeConversationRepository()
        await conv_repo.create(
            ChatConversation(
                id=conv_id,
                tenant_id=tenant_id,
                user_id=user_id,
                title="Nova conversa",
            )
        )
        knowledge_repo = FakeKnowledgeRepository()
        retrieve_uc = RetrieveKnowledgeUseCase(
            knowledge_repo=knowledge_repo,
            embedding_provider=FakeEmbeddingProvider(),
        )
        llm = FakeLLMProvider(
            turns=[
                [
                    LLMStreamEvent(kind="delta", text="Olá! "),
                    LLMStreamEvent(kind="delta", text="Como posso ajudar você no Locus hoje?"),
                    LLMStreamEvent(kind="usage", tokens_in=45, tokens_out=12),
                ]
            ]
        )

        summarize_uc = SummarizeConversationUseCase(
            conversation_repo=conv_repo,
            llm_provider=llm,
        )
        use_case = SendMessageUseCase(
            conversation_repo=conv_repo,
            retrieve_knowledge_use_case=retrieve_uc,
            llm_provider=llm,
            summarize_conversation_use_case=summarize_uc,
        )

        stream = await use_case.execute(
            SendMessageInput(
                conversation_id=conv_id,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role=UserRole.PROFESSOR,
                content="Olá!",
                current_route="/dashboard",
            )
        )
        events = [ev async for ev in stream]

        assert [ev.event for ev in events] == ["delta", "delta", "done"]
        assert events[0].data == {"text": "Olá! "}
        assert events[1].data == {"text": "Como posso ajudar você no Locus hoje?"}
        assert events[2].data["sources"] == []

        assert knowledge_repo.queries == []
        assert conv_repo.conversations[conv_id].title == "Olá!"
        assert len(conv_repo.messages) == 2

        assistant_msg = conv_repo.messages[1]
        assert assistant_msg.role == "assistant"
        assert assistant_msg.content == "Olá! Como posso ajudar você no Locus hoje?"
        assert assistant_msg.sources is None
        assert assistant_msg.tool_calls_used is None
        assert assistant_msg.tokens_in == 45
        assert assistant_msg.tokens_out == 12
        assert assistant_msg.model_name == "fake-gemini-2.5-flash"
        assert assistant_msg.latency_ms is not None

    async def test_help_question_triggers_search_tool_streams_answer_and_persists_sources(
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
                title="Nova conversa",
            )
        )

        retrieved_chunk = RetrievedChunk(
            chunk_id=uuid4(),
            doc_slug="04-chamadas-ao-vivo",
            section_title="Chamadas ao Vivo > Como abrir uma chamada",
            content="Acesse /dashboard/chamadas/nova, escolha a turma e clique em Abrir chamada.",
            routes=["/dashboard/chamadas/nova"],
            score=0.92,
        )
        knowledge_repo = FakeKnowledgeRepository(chunks=[retrieved_chunk])
        retrieve_uc = RetrieveKnowledgeUseCase(
            knowledge_repo=knowledge_repo,
            embedding_provider=FakeEmbeddingProvider(),
        )

        llm = FakeLLMProvider(
            turns=[
                [
                    LLMStreamEvent(
                        kind="tool_call",
                        tool_call=ToolCallRequest(
                            name="search_locus_docs",
                            arguments={"query": "como abrir uma chamada ao vivo"},
                        ),
                    ),
                    LLMStreamEvent(kind="usage", tokens_in=120, tokens_out=15),
                ],
                [
                    LLMStreamEvent(
                        kind="delta",
                        text="Para abrir uma chamada, acesse `/dashboard/chamadas/nova` ",
                    ),
                    LLMStreamEvent(
                        kind="delta",
                        text="e selecione a turma e a sala desejada.",
                    ),
                    LLMStreamEvent(kind="usage", tokens_in=310, tokens_out=40),
                ],
            ]
        )

        summarize_uc = SummarizeConversationUseCase(
            conversation_repo=conv_repo,
            llm_provider=llm,
        )
        use_case = SendMessageUseCase(
            conversation_repo=conv_repo,
            retrieve_knowledge_use_case=retrieve_uc,
            llm_provider=llm,
            summarize_conversation_use_case=summarize_uc,
        )

        stream = await use_case.execute(
            SendMessageInput(
                conversation_id=conv_id,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role=UserRole.PROFESSOR,
                content="Como abrir uma chamada?",
                current_route="/dashboard/turmas",
            )
        )
        events = [ev async for ev in stream]

        assert [ev.event for ev in events] == ["status", "delta", "delta", "done"]
        assert events[0].data["stage"] == "searching_docs"
        assert events[0].data["query"] == "como abrir uma chamada ao vivo"
        assert events[-1].data["sources"] == [
            {
                "doc_slug": "04-chamadas-ao-vivo",
                "section_title": "Chamadas ao Vivo > Como abrir uma chamada",
                "routes": ["/dashboard/chamadas/nova"],
            }
        ]

        assert knowledge_repo.queries == [("como abrir uma chamada ao vivo", UserRole.PROFESSOR)]

        assistant_msg = conv_repo.messages[1]
        assert (
            assistant_msg.content
            == "Para abrir uma chamada, acesse `/dashboard/chamadas/nova` e selecione a turma e a sala desejada."
        )
        assert assistant_msg.sources == [
            {
                "doc_slug": "04-chamadas-ao-vivo",
                "section_title": "Chamadas ao Vivo > Como abrir uma chamada",
                "routes": ["/dashboard/chamadas/nova"],
            }
        ]
        assert assistant_msg.tool_calls_used == [
            {
                "name": "search_locus_docs",
                "arguments": {"query": "como abrir uma chamada ao vivo"},
            }
        ]
        assert assistant_msg.tokens_in == 430
        assert assistant_msg.tokens_out == 55

    async def test_max_iteration_guard_stops_runaway_tool_calls(self) -> None:
        tenant_id = uuid4()
        user_id = uuid4()
        conv_id = uuid4()

        conv_repo = FakeConversationRepository()
        await conv_repo.create(
            ChatConversation(
                id=conv_id,
                tenant_id=tenant_id,
                user_id=user_id,
                title="Conversa existente",
            )
        )

        knowledge_repo = FakeKnowledgeRepository(chunks=[])
        retrieve_uc = RetrieveKnowledgeUseCase(
            knowledge_repo=knowledge_repo,
            embedding_provider=FakeEmbeddingProvider(),
        )

        endless_tool_turn = [
            LLMStreamEvent(
                kind="tool_call",
                tool_call=ToolCallRequest(
                    name="search_locus_docs",
                    arguments={"query": "loop infinito"},
                ),
            )
        ]
        llm = FakeLLMProvider(turns=[endless_tool_turn for _ in range(10)])

        summarize_uc = SummarizeConversationUseCase(
            conversation_repo=conv_repo,
            llm_provider=llm,
        )
        use_case = SendMessageUseCase(
            conversation_repo=conv_repo,
            retrieve_knowledge_use_case=retrieve_uc,
            llm_provider=llm,
            summarize_conversation_use_case=summarize_uc,
            max_tool_iterations=3,
        )

        stream = await use_case.execute(
            SendMessageInput(
                conversation_id=conv_id,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role=UserRole.ADMIN,
                content="Teste de loop",
            )
        )
        events = [ev async for ev in stream]

        status_events = [ev for ev in events if ev.event == "status"]
        assert len(status_events) == 3
        assert events[-2].event == "delta"
        assert events[-2].data["text"] == FALLBACK_MAX_ITERATIONS_TEXT
        assert events[-1].event == "done"

    async def test_provider_failure_emits_error_event_cleanly(self) -> None:
        tenant_id = uuid4()
        user_id = uuid4()
        conv_id = uuid4()

        conv_repo = FakeConversationRepository()
        await conv_repo.create(
            ChatConversation(
                id=conv_id,
                tenant_id=tenant_id,
                user_id=user_id,
                title="Nova conversa",
            )
        )

        retrieve_uc = RetrieveKnowledgeUseCase(
            knowledge_repo=FakeKnowledgeRepository(),
            embedding_provider=FakeEmbeddingProvider(),
        )
        llm = FakeLLMProvider(turns=[], fail_with=RuntimeError("Gemini timeout"))

        summarize_uc = SummarizeConversationUseCase(
            conversation_repo=conv_repo,
            llm_provider=llm,
        )
        use_case = SendMessageUseCase(
            conversation_repo=conv_repo,
            retrieve_knowledge_use_case=retrieve_uc,
            llm_provider=llm,
            summarize_conversation_use_case=summarize_uc,
        )

        stream = await use_case.execute(
            SendMessageInput(
                conversation_id=conv_id,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role=UserRole.ADMIN,
                content="Como configurar uma sala?",
            )
        )
        events = [ev async for ev in stream]

        assert len(events) == 1
        assert events[0].event == "error"
        assert "Não foi possível gerar a resposta" in events[0].data["detail"]

    async def test_validates_empty_message_and_conversation_ownership(self) -> None:
        tenant_id = uuid4()
        user_id = uuid4()
        conv_id = uuid4()

        conv_repo = FakeConversationRepository()
        retrieve_uc = RetrieveKnowledgeUseCase(
            knowledge_repo=FakeKnowledgeRepository(),
            embedding_provider=FakeEmbeddingProvider(),
        )
        fake_llm = FakeLLMProvider(turns=[])
        summarize_uc = SummarizeConversationUseCase(
            conversation_repo=conv_repo,
            llm_provider=fake_llm,
        )
        use_case = SendMessageUseCase(
            conversation_repo=conv_repo,
            retrieve_knowledge_use_case=retrieve_uc,
            llm_provider=fake_llm,
            summarize_conversation_use_case=summarize_uc,
        )

        with pytest.raises(BusinessRuleException):
            await use_case.execute(
                SendMessageInput(
                    conversation_id=conv_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_role=UserRole.PROFESSOR,
                    content="   ",
                )
            )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                SendMessageInput(
                    conversation_id=conv_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_role=UserRole.PROFESSOR,
                    content="Pergunta em conversa inexistente",
                )
            )

    async def test_live_data_tools_multi_step_chain_emits_querying_data_and_scopes_role_tools(
        self,
    ) -> None:
        from unittest.mock import AsyncMock

        tenant_id = uuid4()
        user_id = uuid4()
        conv_id = uuid4()
        class_id = uuid4()
        session_id = uuid4()

        conv_repo = FakeConversationRepository()
        await conv_repo.create(
            ChatConversation(
                id=conv_id,
                tenant_id=tenant_id,
                user_id=user_id,
                title="Nova conversa",
            )
        )
        retrieve_uc = RetrieveKnowledgeUseCase(
            knowledge_repo=FakeKnowledgeRepository(),
            embedding_provider=FakeEmbeddingProvider(),
        )

        fake_executor = AsyncMock()
        fake_executor.execute.side_effect = [
            f"Turmas encontradas: Física I | ID: {class_id}",
            f"Sessão {session_id} | Turma: Física I | Status: closed",
            "Auditoria: PRESENTE: 20 | IRREGULAR: 2 | AUSENTE: 3",
        ]

        llm = FakeLLMProvider(
            turns=[
                [
                    LLMStreamEvent(
                        kind="tool_call",
                        tool_call=ToolCallRequest(
                            name="list_classes",
                            arguments={"search": "Física"},
                        ),
                    )
                ],
                [
                    LLMStreamEvent(
                        kind="tool_call",
                        tool_call=ToolCallRequest(
                            name="list_attendance_sessions",
                            arguments={"subject_class_id": str(class_id)},
                        ),
                    )
                ],
                [
                    LLMStreamEvent(
                        kind="tool_call",
                        tool_call=ToolCallRequest(
                            name="get_session_audit_summary",
                            arguments={
                                "subject_class_id": str(class_id),
                                "session_id": str(session_id),
                            },
                        ),
                    )
                ],
                [
                    LLMStreamEvent(
                        kind="delta",
                        text="Na última chamada de Física I houve 2 presenças irregulares e 3 faltas.",
                    ),
                    LLMStreamEvent(kind="usage", tokens_in=500, tokens_out=30),
                ],
            ]
        )

        summarize_uc = SummarizeConversationUseCase(
            conversation_repo=conv_repo,
            llm_provider=llm,
        )
        use_case = SendMessageUseCase(
            conversation_repo=conv_repo,
            retrieve_knowledge_use_case=retrieve_uc,
            llm_provider=llm,
            summarize_conversation_use_case=summarize_uc,
            tool_executor=fake_executor,
        )

        stream = await use_case.execute(
            SendMessageInput(
                conversation_id=conv_id,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role=UserRole.PROFESSOR,
                content="Há irregulares na última aula de Física?",
            )
        )
        events = [ev async for ev in stream]

        status_events = [ev for ev in events if ev.event == "status"]
        assert [ev.data for ev in status_events] == [
            {"stage": "querying_data", "tool": "list_classes"},
            {"stage": "querying_data", "tool": "list_attendance_sessions"},
            {"stage": "querying_data", "tool": "get_session_audit_summary"},
        ]
        assert events[-1].event == "done"
        assert len(events[-1].data["tool_calls_used"]) == 3

        # Verify role-filtered tools were passed to LLMProvider (8 for PROFESSOR, no admin-only tool)
        first_call_tools = llm.recorded_calls[0]["tools"]
        tool_names = {t["name"] for t in first_call_tools}
        assert len(tool_names) == 8
        assert "get_institution_members_summary" not in tool_names

        # Verify ToolExecutionContext was injected server-side
        first_exec_kwargs = fake_executor.execute.call_args_list[0].kwargs
        assert first_exec_kwargs["ctx"].tenant_id == tenant_id
        assert first_exec_kwargs["ctx"].user_id == user_id
        assert first_exec_kwargs["ctx"].user_role == UserRole.PROFESSOR


class TestGeminiLLMProviderValidation:
    def test_raises_when_api_key_is_empty(self) -> None:
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            GeminiLLMProvider(api_key="   ")
