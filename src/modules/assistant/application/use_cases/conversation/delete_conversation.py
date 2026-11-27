from dataclasses import dataclass
from uuid import UUID

from modules.assistant.domain.repositories.conversation_repository import ConversationRepository
from shared.exceptions import ResourceNotFoundException


@dataclass(frozen=True)
class DeleteConversationInput:
    conversation_id: UUID
    tenant_id: UUID
    user_id: UUID


class DeleteConversationUseCase:
    """Remove uma conversa pertencente ao usuário autenticado na instituição atual."""

    def __init__(self, conversation_repo: ConversationRepository) -> None:
        self._conversation_repo = conversation_repo

    async def execute(self, data: DeleteConversationInput) -> None:
        deleted = await self._conversation_repo.delete(
            conversation_id=data.conversation_id,
            tenant_id=data.tenant_id,
            user_id=data.user_id,
        )
        if not deleted:
            raise ResourceNotFoundException("Conversa não encontrada.")
