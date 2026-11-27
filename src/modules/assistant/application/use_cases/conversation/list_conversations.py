from dataclasses import dataclass
from uuid import UUID

from modules.assistant.domain.entities.chat_conversation import ChatConversation
from modules.assistant.domain.repositories.conversation_repository import ConversationRepository


@dataclass(frozen=True)
class ListConversationsInput:
    tenant_id: UUID
    user_id: UUID
    limit: int = 20
    offset: int = 0


class ListConversationsUseCase:
    """Lista conversas do usuário autenticado na instituição atual (mais recentes primeiro)."""

    def __init__(self, conversation_repo: ConversationRepository) -> None:
        self._conversation_repo = conversation_repo

    async def execute(self, data: ListConversationsInput) -> list[ChatConversation]:
        return await self._conversation_repo.list_by_user(
            tenant_id=data.tenant_id,
            user_id=data.user_id,
            limit=data.limit,
            offset=data.offset,
        )
