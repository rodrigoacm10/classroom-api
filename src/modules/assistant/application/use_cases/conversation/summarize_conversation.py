from dataclasses import dataclass
from uuid import UUID

from modules.assistant.domain.repositories.conversation_repository import ConversationRepository
from modules.assistant.domain.services.llm_provider import LLMProvider

DEFAULT_SUMMARY_WINDOW = 8
DEFAULT_SUMMARY_BATCH_THRESHOLD = 6

SUMMARY_SYSTEM_PROMPT = (
    "Você é um sumarizador interno de conversas do Assistente Locus.\n"
    "Sua tarefa é produzir um resumo conciso em Português do Brasil (pt-BR), com no máximo "
    "250 palavras, combinando o resumo anterior (se houver) com as novas mensagens da conversa.\n"
    "Preserve fatos objetivos essenciais: nomes e IDs de turmas, salas, alunos, chamadas, "
    "dúvidas já respondidas, decisões e pendências.\n"
    "Nunca invente informações que não estejam nas mensagens fornecidas. "
    "Retorne apenas o texto do resumo atualizado, sem títulos ou explicações extras."
)


@dataclass(frozen=True)
class SummarizeConversationInput:
    conversation_id: UUID
    existing_summary: str | None = None
    summary_message_count: int = 0


class SummarizeConversationUseCase:
    """Atualiza de forma incremental o resumo de mensagens fora da janela deslizante."""

    def __init__(
        self,
        *,
        conversation_repo: ConversationRepository,
        llm_provider: LLMProvider,
        history_window: int = DEFAULT_SUMMARY_WINDOW,
        batch_threshold: int = DEFAULT_SUMMARY_BATCH_THRESHOLD,
    ) -> None:
        self._conversation_repo = conversation_repo
        self._llm_provider = llm_provider
        self._history_window = history_window
        self._batch_threshold = batch_threshold

    async def execute(self, data: SummarizeConversationInput) -> str | None:
        total_messages = await self._conversation_repo.count_messages(
            conversation_id=data.conversation_id
        )
        eligible_count = total_messages - self._history_window
        unsummarized_count = eligible_count - data.summary_message_count

        if unsummarized_count < self._batch_threshold:
            return None

        slice_messages = await self._conversation_repo.get_messages_slice(
            conversation_id=data.conversation_id,
            offset=data.summary_message_count,
            limit=unsummarized_count,
        )
        if not slice_messages:
            return None

        transcript_lines = [
            f"{'Usuário' if msg.role == 'user' else 'Assistente'}: {msg.content}"
            for msg in slice_messages
        ]
        transcript = "\n".join(transcript_lines)

        if data.existing_summary and data.existing_summary.strip():
            user_prompt = (
                f"Resumo anterior:\n{data.existing_summary.strip()}\n\n"
                f"Novas mensagens a incorporar ao resumo:\n{transcript}"
            )
        else:
            user_prompt = f"Mensagens iniciais da conversa a resumir:\n{transcript}"

        parts: list[str] = []
        async for event in self._llm_provider.stream_turn(
            system_prompt=SUMMARY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[],
        ):
            if event.kind == "delta" and event.text:
                parts.append(event.text)

        new_summary = "".join(parts).strip()
        if not new_summary:
            return None

        new_count = data.summary_message_count + len(slice_messages)
        await self._conversation_repo.update_summary(
            conversation_id=data.conversation_id,
            summary=new_summary,
            summary_message_count=new_count,
        )
        return new_summary

