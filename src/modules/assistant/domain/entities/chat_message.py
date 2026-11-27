from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

FeedbackRating = Literal["up", "down"]


@dataclass
class ChatMessage:
    """Mensagem persistida em uma conversa do assistente."""

    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant"]
    content: str
    sources: list[dict[str, Any]] | None = None
    tool_calls_used: list[dict[str, Any]] | None = None
    model_name: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    feedback_rating: FeedbackRating | None = None
    feedback_comment: str | None = None
    feedback_updated_at: datetime | None = None
    created_at: datetime | None = None
