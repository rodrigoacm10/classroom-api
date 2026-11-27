from dataclasses import dataclass
from uuid import UUID, uuid4

from modules.assistant.domain.entities.chat_conversation import ChatConversation
from modules.assistant.domain.repositories.conversation_repository import ConversationRepository

DEFAULT_CONVERSATION_TITLE = "Nova conversa"
MAX_CONVERSATION_TITLE_LENGTH = 120


def derive_conversation_title(first_message: str) -> str:
    """Deriva um título limpo e truncado a partir da primeira mensagem do usuário."""
    cleaned = " ".join(first_message.strip().split())
    if not cleaned:
        return DEFAULT_CONVERSATION_TITLE
    if len(cleaned) <= MAX_CONVERSATION_TITLE_LENGTH:
        return cleaned
    return cleaned[: MAX_CONVERSATION_TITLE_LENGTH - 1].rstrip() + "…"


@dataclass(frozen=True)
class CreateConversationInput:
    tenant_id: UUID
    user_id: UUID
    title: str | None = None


class CreateConversationUseCase:
    """Cria uma nova conversa escopada por (tenant_id, user_id)."""

    def __init__(self, conversation_repo: ConversationRepository) -> None:
        self._conversation_repo = conversation_repo

    async def execute(self, data: CreateConversationInput) -> ChatConversation:
        raw_title = (data.title or "").strip()
        title = derive_conversation_title(raw_title) if raw_title else DEFAULT_CONVERSATION_TITLE
        conversation = ChatConversation(
            id=uuid4(),
            tenant_id=data.tenant_id,
            user_id=data.user_id,
            title=title,
        )
        return await self._conversation_repo.create(conversation)
