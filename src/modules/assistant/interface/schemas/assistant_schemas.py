from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str | None = Field(
        default=None,
        max_length=120,
        description="Título opcional para a conversa. Se omitido, inicia como 'Nova conversa'.",
    )


class SourceCitationResponse(BaseModel):
    doc_slug: str
    section_title: str
    routes: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChatMessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceCitationResponse] | None = None
    tool_calls_used: list[dict[str, Any]] | None = None
    model_name: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    feedback_rating: Literal["up", "down"] | None = None
    feedback_comment: str | None = None
    feedback_updated_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConversationSummaryResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID
    title: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConversationDetailResponse(ConversationSummaryResponse):
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class SendMessageRequest(BaseModel):
    content: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Pergunta ou mensagem do usuário em português.",
    )
    current_route: str | None = Field(
        default=None,
        max_length=255,
        description="Rota atual do painel web (ex.: '/dashboard/salas').",
    )


class MessageFeedbackRequest(BaseModel):
    rating: Literal["up", "down"] | None = Field(
        default=None,
        description="Avaliação da resposta ('up', 'down' ou null para remover).",
    )
    comment: str | None = Field(
        default=None,
        max_length=500,
        description="Comentário opcional sobre a resposta do assistente.",
    )


class MessageFeedbackResponse(BaseModel):
    message_id: UUID
    feedback_rating: Literal["up", "down"] | None = None
    feedback_comment: str | None = None
    feedback_updated_at: datetime | None = None
