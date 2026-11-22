from dataclasses import dataclass
from uuid import UUID

from modules.assistant.domain.entities.chat_conversation import ChatConversation
from modules.assistant.domain.repositories.conversation_repository import ConversationRepository
from shared.exceptions import ResourceNotFoundException


@dataclass(frozen=True)
class GetConversationInput:
    conversation_id: UUID
    tenant_id: UUID
    user_id: UUID


class GetConversationUseCase:
    """Busca uma conversa e suas mensagens garantindo isolamento por tenant e usuário."""

    def __init__(self, conversation_repo: ConversationRepository) -> None:
        self._conversation_repo = conversation_repo

    async def execute(self, data: GetConversationInput) -> ChatConversation:
        conversation = await self._conversation_repo.get_by_id(
            conversation_id=data.conversation_id,
            tenant_id=data.tenant_id,
            user_id=data.user_id,
            include_messages=True,
        )
        if conversation is None:
            raise ResourceNotFoundException("Conversa não encontrada.")
        return conversation
