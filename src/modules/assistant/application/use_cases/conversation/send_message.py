import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

from modules.assistant.application.prompts import build_system_prompt
from modules.assistant.application.use_cases.conversation.create_conversation import (
    DEFAULT_CONVERSATION_TITLE,
    derive_conversation_title,
)
from modules.assistant.application.use_cases.knowledge.retrieve_knowledge import (
    RetrieveKnowledgeInput,
    RetrieveKnowledgeUseCase,
)
from modules.assistant.domain.entities.chat_message import ChatMessage
from modules.assistant.domain.entities.knowledge_chunk import SourceCitation
from modules.assistant.domain.entities.llm_events import ToolCallRequest
from modules.assistant.domain.repositories.conversation_repository import ConversationRepository
from modules.assistant.domain.services.llm_provider import LLMProvider
from modules.assistant.domain.tools import (
    SEARCH_LOCUS_DOCS_TOOL_NAME,
    format_retrieved_chunks_for_tool,
    get_assistant_tools,
)
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ResourceNotFoundException

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 3
DEFAULT_HISTORY_WINDOW = 8
FALLBACK_MAX_ITERATIONS_TEXT = (
    "Não foi possível concluir a consulta à documentação neste momento. "
    "Por favor, reformule sua pergunta de forma mais específica."
)


@dataclass(frozen=True)
class SendMessageInput:
    conversation_id: UUID
    tenant_id: UUID
    user_id: UUID
    user_role: UserRole
    content: str
    current_route: str | None = None


@dataclass(frozen=True)
class AssistantSSEEvent:
    """Evento de streaming (SSE) emitido pelo SendMessageUseCase."""

    event: Literal["status", "delta", "done", "error"]
    data: dict[str, Any]


class SendMessageUseCase:
    """Executa o loop Agentic RAG com tool calling, janela deslizante e persistência."""

    def __init__(
        self,
        *,
        conversation_repo: ConversationRepository,
        retrieve_knowledge_use_case: RetrieveKnowledgeUseCase,
        llm_provider: LLMProvider,
        history_window: int = DEFAULT_HISTORY_WINDOW,
        max_tool_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> None:
        self._conversation_repo = conversation_repo
        self._retrieve_knowledge = retrieve_knowledge_use_case
        self._llm_provider = llm_provider
        self._history_window = history_window
        self._max_tool_iterations = max_tool_iterations

    async def execute(self, data: SendMessageInput) -> AsyncIterator[AssistantSSEEvent]:
        cleaned_content = data.content.strip()
        if not cleaned_content:
            raise BusinessRuleException("A mensagem não pode estar vazia.")

        conversation = await self._conversation_repo.get_by_id(
            conversation_id=data.conversation_id,
            tenant_id=data.tenant_id,
            user_id=data.user_id,
            include_messages=False,
        )
        if conversation is None:
            raise ResourceNotFoundException("Conversa não encontrada.")

        recent_messages = await self._conversation_repo.get_recent_messages(
            conversation_id=data.conversation_id,
            limit=self._history_window,
        )

        await self._conversation_repo.add_message(
            ChatMessage(
                id=uuid4(),
                conversation_id=data.conversation_id,
                role="user",
                content=cleaned_content,
            )
        )

        if not recent_messages and conversation.title == DEFAULT_CONVERSATION_TITLE:
            await self._conversation_repo.update_title(
                conversation_id=data.conversation_id,
                title=derive_conversation_title(cleaned_content),
            )

        return self._stream_agentic_loop(
            data=data,
            cleaned_content=cleaned_content,
            recent_messages=recent_messages,
        )

    async def _stream_agentic_loop(
        self,
        *,
        data: SendMessageInput,
        cleaned_content: str,
        recent_messages: list[ChatMessage],
    ) -> AsyncIterator[AssistantSSEEvent]:
        start_perf = time.perf_counter()
        system_prompt = build_system_prompt(
            user_role=data.user_role,
            current_route=data.current_route,
        )
        tools = get_assistant_tools()

        llm_messages: list[dict[str, Any]] = [
            {"role": msg.role, "content": msg.content} for msg in recent_messages
        ]
        llm_messages.append({"role": "user", "content": cleaned_content})

        accumulated_text: list[str] = []
        tool_calls_used: list[dict[str, Any]] = []
        citations_by_key: dict[tuple[str, str], SourceCitation] = {}
        total_tokens_in = 0
        total_tokens_out = 0
        has_token_usage = False

        try:
            iterations = 0
            while True:
                pending_tool_calls: list[ToolCallRequest] = []

                async for event in self._llm_provider.stream_turn(
                    system_prompt=system_prompt,
                    messages=llm_messages,
                    tools=tools,
                ):
                    if event.kind == "delta" and event.text:
                        accumulated_text.append(event.text)
                        yield AssistantSSEEvent(
                            event="delta",
                            data={"text": event.text},
                        )
                    elif event.kind == "tool_call" and event.tool_call is not None:
                        pending_tool_calls.append(event.tool_call)
                    elif event.kind == "usage":
                        if event.tokens_in is not None:
                            total_tokens_in += event.tokens_in
                            has_token_usage = True
                        if event.tokens_out is not None:
                            total_tokens_out += event.tokens_out
                            has_token_usage = True

                if not pending_tool_calls:
                    break

                if iterations >= self._max_tool_iterations:
                    if not accumulated_text:
                        accumulated_text.append(FALLBACK_MAX_ITERATIONS_TEXT)
                        yield AssistantSSEEvent(
                            event="delta",
                            data={"text": FALLBACK_MAX_ITERATIONS_TEXT},
                        )
                    break

                iterations += 1
                llm_messages.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "name": tc.name,
                                "arguments": dict(tc.arguments),
                                "provider_part": tc.provider_part,
                            }
                            for tc in pending_tool_calls
                        ],
                    }
                )

                for tc in pending_tool_calls:
                    tool_calls_used.append({"name": tc.name, "arguments": dict(tc.arguments)})
                    if tc.name == SEARCH_LOCUS_DOCS_TOOL_NAME:
                        query = str(tc.arguments.get("query", "")).strip() or cleaned_content
                        yield AssistantSSEEvent(
                            event="status",
                            data={
                                "stage": "searching_docs",
                                "tool": SEARCH_LOCUS_DOCS_TOOL_NAME,
                                "query": query,
                            },
                        )
                        retrieved = await self._retrieve_knowledge.execute(
                            RetrieveKnowledgeInput(
                                query=query,
                                user_role=data.user_role,
                            )
                        )
                        for chunk in retrieved:
                            key = (chunk.doc_slug, chunk.section_title)
                            if key not in citations_by_key:
                                citations_by_key[key] = SourceCitation(
                                    doc_slug=chunk.doc_slug,
                                    section_title=chunk.section_title,
                                    routes=list(chunk.routes),
                                )
                        tool_output = format_retrieved_chunks_for_tool(retrieved)
                    else:
                        tool_output = f"Ferramenta '{tc.name}' não suportada."

                    llm_messages.append(
                        {
                            "role": "tool",
                            "name": tc.name,
                            "content": tool_output,
                        }
                    )

        except Exception:
            logger.exception(
                "Erro ao gerar resposta do Assistente Locus (conversa=%s, modelo=%s)",
                data.conversation_id,
                self._llm_provider.model_name,
            )
            partial_text = "".join(accumulated_text).strip()
            if len(partial_text) < 40:
                yield AssistantSSEEvent(
                    event="error",
                    data={
                        "detail": (
                            "Não foi possível gerar a resposta do assistente no momento. "
                            "Tente novamente em instantes."
                        )
                    },
                )
                return
            logger.warning(
                "Stream interrompido após %d caracteres; preservando resposta parcial na conversa %s.",
                len(partial_text),
                data.conversation_id,
            )

        latency_ms = int((time.perf_counter() - start_perf) * 1000)
        final_content = "".join(accumulated_text).strip()
        sources_payload = [
            {
                "doc_slug": citation.doc_slug,
                "section_title": citation.section_title,
                "routes": citation.routes,
            }
            for citation in citations_by_key.values()
        ]

        assistant_msg = await self._conversation_repo.add_message(
            ChatMessage(
                id=uuid4(),
                conversation_id=data.conversation_id,
                role="assistant",
                content=final_content,
                sources=sources_payload if sources_payload else None,
                tool_calls_used=tool_calls_used if tool_calls_used else None,
                model_name=self._llm_provider.model_name,
                tokens_in=total_tokens_in if has_token_usage else None,
                tokens_out=total_tokens_out if has_token_usage else None,
                latency_ms=latency_ms,
            )
        )

        yield AssistantSSEEvent(
            event="done",
            data={
                "message_id": str(assistant_msg.id),
                "sources": sources_payload,
                "tool_calls_used": tool_calls_used,
            },
        )
