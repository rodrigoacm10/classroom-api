from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.chat_conversation import ChatConversationModel
from infra.database.models.chat_message import ChatMessageModel
from modules.assistant.domain.entities.chat_conversation import ChatConversation
from modules.assistant.domain.entities.chat_message import ChatMessage


class ConversationSQLAlchemyRepository:
    """Repositório PostgreSQL para conversas e mensagens escopadas por (tenant_id, user_id)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, conversation: ChatConversation) -> ChatConversation:
        now = datetime.now(UTC)
        model = ChatConversationModel(
            id=conversation.id,
            tenant_id=conversation.tenant_id,
            user_id=conversation.user_id,
            title=conversation.title,
            created_at=conversation.created_at or now,
            updated_at=conversation.updated_at or now,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_conversation_entity(model)

    async def list_by_user(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ChatConversation]:
        stmt = (
            select(ChatConversationModel)
            .where(
                ChatConversationModel.tenant_id == tenant_id,
                ChatConversationModel.user_id == user_id,
            )
            .order_by(
                ChatConversationModel.updated_at.desc(),
                ChatConversationModel.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [self._to_conversation_entity(model) for model in result.scalars().all()]

    async def get_by_id(
        self,
        *,
        conversation_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        include_messages: bool = True,
    ) -> ChatConversation | None:
        stmt = select(ChatConversationModel).where(
            ChatConversationModel.id == conversation_id,
            ChatConversationModel.tenant_id == tenant_id,
            ChatConversationModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None

        messages: list[ChatMessage] = []
        if include_messages:
            msg_stmt = (
                select(ChatMessageModel)
                .where(ChatMessageModel.conversation_id == conversation_id)
                .order_by(ChatMessageModel.created_at.asc())
            )
            msg_result = await self._session.execute(msg_stmt)
            messages = [self._to_message_entity(m) for m in msg_result.scalars().all()]

        return self._to_conversation_entity(model, messages=messages)

    async def update_title(self, *, conversation_id: UUID, title: str) -> None:
        stmt = (
            update(ChatConversationModel)
            .where(ChatConversationModel.id == conversation_id)
            .values(title=title, updated_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def delete(
        self,
        *,
        conversation_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
    ) -> bool:
        stmt = delete(ChatConversationModel).where(
            ChatConversationModel.id == conversation_id,
            ChatConversationModel.tenant_id == tenant_id,
            ChatConversationModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return bool(getattr(result, "rowcount", 0))

    async def add_message(self, message: ChatMessage) -> ChatMessage:
        now = datetime.now(UTC)
        model = ChatMessageModel(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role,
            content=message.content,
            sources=message.sources,
            tool_calls_used=message.tool_calls_used,
            model_name=message.model_name,
            tokens_in=message.tokens_in,
            tokens_out=message.tokens_out,
            latency_ms=message.latency_ms,
            created_at=message.created_at or now,
        )
        self._session.add(model)

        touch_stmt = (
            update(ChatConversationModel)
            .where(ChatConversationModel.id == message.conversation_id)
            .values(updated_at=now)
        )
        await self._session.execute(touch_stmt)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_message_entity(model)

    async def get_recent_messages(
        self,
        *,
        conversation_id: UUID,
        limit: int = 8,
    ) -> list[ChatMessage]:
        stmt = (
            select(ChatMessageModel)
            .where(ChatMessageModel.conversation_id == conversation_id)
            .order_by(ChatMessageModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = list(result.scalars().all())
        models.reverse()
        return [self._to_message_entity(m) for m in models]

    @staticmethod
    def _to_conversation_entity(
        model: ChatConversationModel,
        messages: list[ChatMessage] | None = None,
    ) -> ChatConversation:
        return ChatConversation(
            id=model.id,
            tenant_id=model.tenant_id,
            user_id=model.user_id,
            title=model.title,
            created_at=model.created_at,
            updated_at=model.updated_at,
            messages=messages if messages is not None else [],
        )

    @staticmethod
    def _to_message_entity(model: ChatMessageModel) -> ChatMessage:
        role = "assistant" if model.role == "assistant" else "user"
        return ChatMessage(
            id=model.id,
            conversation_id=model.conversation_id,
            role=role,
            content=model.content,
            sources=list(model.sources) if model.sources is not None else None,
            tool_calls_used=(
                list(model.tool_calls_used) if model.tool_calls_used is not None else None
            ),
            model_name=model.model_name,
            tokens_in=model.tokens_in,
            tokens_out=model.tokens_out,
            latency_ms=model.latency_ms,
            created_at=model.created_at,
        )
