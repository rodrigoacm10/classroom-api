from typing import Protocol
from uuid import UUID

from modules.assistant.domain.entities.chat_conversation import ChatConversation
from modules.assistant.domain.entities.chat_message import ChatMessage


class ConversationRepository(Protocol):
    """Contrato de persistência de conversas e mensagens escopadas por tenant e usuário."""

    async def create(self, conversation: ChatConversation) -> ChatConversation: ...

    async def list_by_user(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ChatConversation]: ...

    async def get_by_id(
        self,
        *,
        conversation_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        include_messages: bool = True,
    ) -> ChatConversation | None: ...

    async def update_title(self, *, conversation_id: UUID, title: str) -> None: ...

    async def delete(
        self,
        *,
        conversation_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
    ) -> bool: ...

    async def add_message(self, message: ChatMessage) -> ChatMessage: ...

    async def get_recent_messages(
        self,
        *,
        conversation_id: UUID,
        limit: int = 8,
    ) -> list[ChatMessage]: ...
