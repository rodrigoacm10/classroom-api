import logging

from modules.attendance.domain.events.attendance_events import (
    AttendanceSessionClosedEvent,
    AttendanceSessionOpenedEvent,
)
from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository

logger = logging.getLogger(__name__)


class AttendancePushNotificationHandler:
    """
    Escuta eventos de chamada (abertura e fechamento) e despacha notificações
    push para os alunos matriculados na turma via Celery.

    Este handler é a única camada que conhece:
      - EnrollmentRepository (para buscar tokens FCM)
      - Celery task send_push_notification (infraestrutura de mensageria)
      - O conteúdo textual de cada notificação

    Os Use Cases que publicam os eventos não conhecem este handler.
    """

    def __init__(self, enrollment_repo: EnrollmentRepository) -> None:
        self.enrollment_repo = enrollment_repo

    async def on_session_opened(self, event: AttendanceSessionOpenedEvent) -> None:
        """Envia push de 'chamada aberta' para todos os alunos ativos da turma."""
        from infra.tasks.notification_tasks import send_push_notification

        tokens = await self.enrollment_repo.find_active_fcm_tokens(event.subject_class_id)
        if not tokens:
            logger.info(
                "on_session_opened: no FCM tokens for subject_class_id=%s, skipping.",
                event.subject_class_id,
            )
            return

        send_push_notification.delay(
            title=f"📋 Chamada Aberta — {event.subject_class_name}",
            body=(
                f"O professor iniciou a chamada! Você tem {event.duration_minutes} "
                f"minutos. Código: {event.day_code}"
            ),
            data={
                "type": "ATTENDANCE_OPENED",
                "day_code": event.day_code,
                "subject_class_name": event.subject_class_name,
                "duration_minutes": str(event.duration_minutes),
            },
            fcm_tokens=tokens,
        )

    async def on_session_closed(self, event: AttendanceSessionClosedEvent) -> None:
        """Envia push de 'chamada encerrada' para todos os alunos ativos da turma."""
        from infra.tasks.notification_tasks import send_push_notification

        tokens = await self.enrollment_repo.find_active_fcm_tokens(event.subject_class_id)
        if not tokens:
            logger.info(
                "on_session_closed: no FCM tokens for subject_class_id=%s, skipping.",
                event.subject_class_id,
            )
            return

        send_push_notification.delay(
            title=f"🔒 Chamada Encerrada — {event.subject_class_name}",
            body="A janela de confirmação de presença foi encerrada pelo professor.",
            data={
                "type": "ATTENDANCE_CLOSED",
                "subject_class_name": event.subject_class_name,
            },
            fcm_tokens=tokens,
        )


def register_attendance_event_handlers(dispatcher) -> None:
    """
    Registra os ouvintes (listeners) dos eventos de chamada no EventDispatcher.

    Para cada evento disparado, abre uma sessão de banco independente (AsyncSessionLocal)
    para buscar os alunos e despachar as notificações push via Celery.
    """

    async def _on_session_opened(event: AttendanceSessionOpenedEvent) -> None:
        from infra.database.session import AsyncSessionLocal
        from modules.enrollment.infra.repositories.enrollment_sqlalchemy_repository import (
            EnrollmentSQLAlchemyRepository,
        )

        async with AsyncSessionLocal() as db:
            handler = AttendancePushNotificationHandler(
                enrollment_repo=EnrollmentSQLAlchemyRepository(session=db)
            )
            await handler.on_session_opened(event)

    async def _on_session_closed(event: AttendanceSessionClosedEvent) -> None:
        from infra.database.session import AsyncSessionLocal
        from modules.enrollment.infra.repositories.enrollment_sqlalchemy_repository import (
            EnrollmentSQLAlchemyRepository,
        )

        async with AsyncSessionLocal() as db:
            handler = AttendancePushNotificationHandler(
                enrollment_repo=EnrollmentSQLAlchemyRepository(session=db)
            )
            await handler.on_session_closed(event)

    dispatcher.register(AttendanceSessionOpenedEvent, _on_session_opened)
    dispatcher.register(AttendanceSessionClosedEvent, _on_session_closed)

