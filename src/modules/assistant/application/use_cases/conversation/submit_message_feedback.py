from dataclasses import dataclass
from uuid import UUID

from modules.assistant.domain.entities.chat_message import ChatMessage, FeedbackRating
from modules.assistant.domain.repositories.conversation_repository import ConversationRepository
from shared.exceptions import BusinessRuleException, ResourceNotFoundException

MAX_FEEDBACK_COMMENT_LENGTH = 500


@dataclass(frozen=True)
class SubmitMessageFeedbackInput:
    conversation_id: UUID
    message_id: UUID
    tenant_id: UUID
    user_id: UUID
    rating: FeedbackRating | None
    comment: str | None = None


class SubmitMessageFeedbackUseCase:
    """Registra, atualiza ou remove avaliação (thumbs up / down) em uma mensagem do assistente."""

    def __init__(self, conversation_repo: ConversationRepository) -> None:
        self._conversation_repo = conversation_repo

    async def execute(self, data: SubmitMessageFeedbackInput) -> ChatMessage:
        message = await self._conversation_repo.get_message_by_id(
            conversation_id=data.conversation_id,
            message_id=data.message_id,
            tenant_id=data.tenant_id,
            user_id=data.user_id,
        )
        if message is None:
            raise ResourceNotFoundException("Mensagem não encontrada.")

        if message.role != "assistant":
            raise BusinessRuleException("Apenas mensagens do assistente podem receber avaliação.")

        cleaned_comment: str | None = None
        if data.rating is not None and data.comment is not None:
            stripped = data.comment.strip()
            if len(stripped) > MAX_FEEDBACK_COMMENT_LENGTH:
                raise BusinessRuleException(
                    f"O comentário de avaliação deve ter no máximo {MAX_FEEDBACK_COMMENT_LENGTH} caracteres."
                )
            cleaned_comment = stripped if stripped else None

        updated = await self._conversation_repo.set_message_feedback(
            conversation_id=data.conversation_id,
            message_id=data.message_id,
            tenant_id=data.tenant_id,
            user_id=data.user_id,
            rating=data.rating,
            comment=cleaned_comment,
        )
        if updated is None:
            raise ResourceNotFoundException("Mensagem não encontrada.")
        return updated

