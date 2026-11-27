from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from modules.assistant.domain.entities.chat_message import ChatMessage


@dataclass
class ChatConversation:
    """Conversa do assistente escopada por (tenant_id, user_id)."""

    id: UUID
    tenant_id: UUID
    user_id: UUID
    title: str
    summary: str | None = None
    summary_message_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    messages: list[ChatMessage] = field(default_factory=list)
