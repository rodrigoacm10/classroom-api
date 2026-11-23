import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from infra.database.session import get_db
from modules.assistant.application.tool_executor import AssistantToolExecutor
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
from modules.assistant.application.use_cases.conversation.submit_message_feedback import (
    SubmitMessageFeedbackInput,
    SubmitMessageFeedbackUseCase,
)
from modules.assistant.application.use_cases.conversation.summarize_conversation import (
    SummarizeConversationUseCase,
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
    MessageFeedbackRequest,
    MessageFeedbackResponse,
    SendMessageRequest,
)
from modules.attendance.application.use_cases.get_attendance_metrics import (
    GetAttendanceMetricsUseCase,
)
from modules.attendance.application.use_cases.get_session import GetAttendanceSessionUseCase
from modules.attendance.application.use_cases.list_session_roster import ListSessionRosterUseCase
from modules.attendance.application.use_cases.list_tenant_sessions import (
    ListTenantAttendanceSessionsUseCase,
)
from modules.attendance.infra.repositories.record_sqlalchemy_repository import (
    RecordSQLAlchemyRepository,
)
from modules.attendance.infra.repositories.session_sqlalchemy_repository import (
    SessionSQLAlchemyRepository,
)
from modules.report.application.use_cases.generate_class_report import GenerateClassReportUseCase
from modules.report.application.use_cases.get_dashboard_metrics import GetDashboardMetricsUseCase
from modules.report.application.use_cases.get_student_report import GetStudentReportUseCase
from modules.report.infra.repositories.dashboard_metrics_sqlalchemy_repository import (
    DashboardMetricsSQLAlchemyRepository,
)
from modules.report.infra.repositories.report_data_repository import ReportDataRepository
from modules.report.infra.repositories.report_generation_log_repository import (
    ReportGenerationLogRepository,
)
from modules.report.infra.strategy_factory import get_report_compute_strategy
from modules.room.application.use_cases.get_room_metrics import GetRoomMetricsUseCase
from modules.room.application.use_cases.list_rooms import ListRoomsUseCase
from modules.room.infra.repositories.room_sqlalchemy_repository import RoomSQLAlchemyRepository
from modules.subject_class.application.use_cases.list_subject_classes import (
    ListSubjectClassesUseCase,
)
from modules.subject_class.infra.repositories.subject_class_sqlalchemy_repository import (
    SubjectClassSQLAlchemyRepository,
)
from modules.tenant.application.use_cases.get_members_metrics import GetMembersMetricsUseCase
from modules.tenant.application.use_cases.get_tenant_invites_metrics import (
    GetTenantInvitesMetricsUseCase,
)
from modules.tenant.application.use_cases.list_students import ListStudentsUseCase
from modules.tenant.infra.repositories.tenant_invite_sqlalchemy_repository import (
    TenantInviteSQLAlchemyRepository,
)
from modules.tenant.infra.repositories.tenant_member_sqlalchemy_repository import (
    TenantMemberSQLAlchemyRepository,
)
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import (
    TenantSQLAlchemyRepository,
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


def _build_tool_executor(db: AsyncSession) -> AssistantToolExecutor:
    """Instancia o executor de ferramentas operacionais read-only com os repositórios da sessão."""
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    invite_repo = TenantInviteSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    session_repo = SessionSQLAlchemyRepository(session=db)
    record_repo = RecordSQLAlchemyRepository(session=db)
    room_repo = RoomSQLAlchemyRepository(session=db)
    dashboard_metrics_repo = DashboardMetricsSQLAlchemyRepository(session=db)
    report_data_repo = ReportDataRepository(session=db)
    report_log_repo = ReportGenerationLogRepository(session=db)

    return AssistantToolExecutor(
        get_dashboard_metrics=GetDashboardMetricsUseCase(
            metrics_repo=dashboard_metrics_repo,
            tenant_repo=tenant_repo,
        ),
        get_attendance_metrics=GetAttendanceMetricsUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
        ),
        list_subject_classes=ListSubjectClassesUseCase(
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        ),
        generate_class_report=GenerateClassReportUseCase(
            report_data_repo=report_data_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            compute_strategy=get_report_compute_strategy(),
            log_repo=report_log_repo,
        ),
        list_tenant_sessions=ListTenantAttendanceSessionsUseCase(
            session_repo=session_repo,
            tenant_repo=tenant_repo,
        ),
        get_session=GetAttendanceSessionUseCase(
            session_repo=session_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
        ),
        list_session_roster=ListSessionRosterUseCase(
            record_repo=record_repo,
            session_repo=session_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
        ),
        list_students=ListStudentsUseCase(
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        ),
        get_student_report=GetStudentReportUseCase(
            report_data_repo=report_data_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
        ),
        list_rooms=ListRoomsUseCase(
            room_repo=room_repo,
            tenant_repo=tenant_repo,
        ),
        get_room_metrics=GetRoomMetricsUseCase(
            room_repo=room_repo,
            tenant_repo=tenant_repo,
        ),
        get_members_metrics=GetMembersMetricsUseCase(
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        ),
        get_tenant_invites_metrics=GetTenantInvitesMetricsUseCase(
            tenant_repo=tenant_repo,
            invite_repo=invite_repo,
        ),
        subject_class_repo=subject_class_repo,
        member_repo=member_repo,
    )


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
    summarize_uc = SummarizeConversationUseCase(
        conversation_repo=conversation_repo,
        llm_provider=llm_provider,
    )
    use_case = SendMessageUseCase(
        conversation_repo=conversation_repo,
        retrieve_knowledge_use_case=retrieve_uc,
        llm_provider=llm_provider,
        summarize_conversation_use_case=summarize_uc,
        tool_executor=_build_tool_executor(db),
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


@router.put(
    "/conversations/{conversation_id}/messages/{message_id}/feedback",
    response_model=MessageFeedbackResponse,
)
async def submit_message_feedback(
    conversation_id: UUID,
    message_id: UUID,
    body: MessageFeedbackRequest,
    ctx: AuthContext = Depends(require_role(*ALLOWED_ASSISTANT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> MessageFeedbackResponse:
    """Registra, altera ou remove avaliação (thumbs up / down) em uma mensagem do assistente."""
    assert ctx.tenant_id is not None
    repo = ConversationSQLAlchemyRepository(session=db)
    use_case = SubmitMessageFeedbackUseCase(conversation_repo=repo)
    updated = await use_case.execute(
        SubmitMessageFeedbackInput(
            conversation_id=conversation_id,
            message_id=message_id,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user.id,
            rating=body.rating,
            comment=body.comment,
        )
    )
    return MessageFeedbackResponse(
        message_id=updated.id,
        feedback_rating=updated.feedback_rating,
        feedback_comment=updated.feedback_comment,
        feedback_updated_at=updated.feedback_updated_at,
    )
