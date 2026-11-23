import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from infra.database.session import get_db
from modules.assistant.application.use_cases.conversation.create_conversation import (
    CreateConversationInput,
    CreateConversationUseCase,
)
from modules.assistant.application.use_cases.conversation.delete_conversation import (
    DeleteConversationInput,
    DeleteConversationUseCase,
)
from modules.assistant.application.use_cases.conversation.get_conversation import (
    GetConversationInput,
    GetConversationUseCase,
)
from modules.assistant.application.use_cases.conversation.list_conversations import (
    ListConversationsInput,
    ListConversationsUseCase,
)
from modules.assistant.application.use_cases.conversation.send_message import (
    SendMessageInput,
    SendMessageUseCase,
)
from modules.assistant.application.use_cases.knowledge.retrieve_knowledge import (
    RetrieveKnowledgeUseCase,
)
from modules.assistant.domain.services.embedding_provider import EmbeddingProvider
from modules.assistant.domain.services.llm_provider import LLMProvider
from modules.assistant.infra.gemini.provider_factory import (
    get_embedding_provider,
    get_llm_provider,
)
from modules.assistant.infra.repositories.conversation_sqlalchemy_repository import (
    ConversationSQLAlchemyRepository,
)
from modules.assistant.infra.repositories.knowledge_sqlalchemy_repository import (
    KnowledgeSQLAlchemyRepository,
)
from modules.assistant.interface.schemas.assistant_schemas import (
    ConversationDetailResponse,
    ConversationSummaryResponse,
    CreateConversationRequest,
    SendMessageRequest,
)
from security.dependencies.current_user import AuthContext
from security.dependencies.require_role import require_role
from security.rate_limiter import limiter
from shared.enums.user_role import UserRole

ALLOWED_ASSISTANT_ROLES = (
    UserRole.ADMIN,
    UserRole.COORDENADOR,
    UserRole.PROFESSOR,
)

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post(
    "/conversations",
    response_model=ConversationSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    body: CreateConversationRequest = CreateConversationRequest(),
    ctx: AuthContext = Depends(require_role(*ALLOWED_ASSISTANT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ConversationSummaryResponse:
    """Cria uma nova conversa do assistente para o usuário autenticado na tenant ativa."""
    assert ctx.tenant_id is not None
    repo = ConversationSQLAlchemyRepository(session=db)
    use_case = CreateConversationUseCase(conversation_repo=repo)
    conversation = await use_case.execute(
        CreateConversationInput(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user.id,
            title=body.title,
        )
    )
    return ConversationSummaryResponse.model_validate(conversation)


@router.get(
    "/conversations",
    response_model=list[ConversationSummaryResponse],
)
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=50, description="Quantidade máxima de conversas"),
    offset: int = Query(default=0, ge=0, description="Deslocamento para paginação"),
    ctx: AuthContext = Depends(require_role(*ALLOWED_ASSISTANT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationSummaryResponse]:
    """Lista as conversas do usuário autenticado na tenant ativa (mais recentes primeiro)."""
    assert ctx.tenant_id is not None
    repo = ConversationSQLAlchemyRepository(session=db)
    use_case = ListConversationsUseCase(conversation_repo=repo)
    conversations = await use_case.execute(
        ListConversationsInput(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user.id,
            limit=limit,
            offset=offset,
        )
    )
    return [ConversationSummaryResponse.model_validate(c) for c in conversations]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
)
async def get_conversation(
    conversation_id: UUID,
    ctx: AuthContext = Depends(require_role(*ALLOWED_ASSISTANT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailResponse:
    """Retorna os metadados e o histórico de mensagens de uma conversa do usuário."""
    assert ctx.tenant_id is not None
    repo = ConversationSQLAlchemyRepository(session=db)
    use_case = GetConversationUseCase(conversation_repo=repo)
    conversation = await use_case.execute(
        GetConversationInput(
            conversation_id=conversation_id,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user.id,
        )
    )
    return ConversationDetailResponse.model_validate(conversation)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: UUID,
    ctx: AuthContext = Depends(require_role(*ALLOWED_ASSISTANT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove uma conversa pertencente ao usuário autenticado na tenant ativa."""
    assert ctx.tenant_id is not None
    repo = ConversationSQLAlchemyRepository(session=db)
    use_case = DeleteConversationUseCase(conversation_repo=repo)
    await use_case.execute(
        DeleteConversationInput(
            conversation_id=conversation_id,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user.id,
        )
    )


@router.post("/conversations/{conversation_id}/messages")
@limiter.limit(settings.assistant_rate_limit)
async def send_message(
    request: Request,
    conversation_id: UUID,
    body: SendMessageRequest,
    ctx: AuthContext = Depends(require_role(*ALLOWED_ASSISTANT_ROLES)),
    db: AsyncSession = Depends(get_db),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
) -> StreamingResponse:
    """
    Envia uma mensagem para o assistente e transmite a resposta via Server-Sent Events (SSE):
    - `event: status` -> `{"stage": "searching_docs"}`
    - `event: delta`  -> `{"text": "..."}`
    - `event: done`   -> `{"message_id": "...", "sources": [...]}`
    - `event: error`  -> `{"detail": "..."}`
    """
    assert ctx.tenant_id is not None
    assert ctx.role is not None

    conversation_repo = ConversationSQLAlchemyRepository(session=db)
    knowledge_repo = KnowledgeSQLAlchemyRepository(session=db)
    retrieve_uc = RetrieveKnowledgeUseCase(
        knowledge_repo=knowledge_repo,
        embedding_provider=embedding_provider,
    )
    use_case = SendMessageUseCase(
        conversation_repo=conversation_repo,
        retrieve_knowledge_use_case=retrieve_uc,
        llm_provider=llm_provider,
    )

    event_stream = await use_case.execute(
        SendMessageInput(
            conversation_id=conversation_id,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user.id,
            user_role=ctx.role,
            content=body.content,
            current_route=body.current_route,
        )
    )

    async def sse_generator() -> AsyncIterator[str]:
        async for sse_event in event_stream:
            payload = json.dumps(sse_event.data, ensure_ascii=False)
            yield f"event: {sse_event.event}\ndata: {payload}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
