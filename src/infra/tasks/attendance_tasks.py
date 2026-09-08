import asyncio
import logging
from celery import Task

from infra.database.session import AsyncSessionLocal
from infra.tasks.celery_app import celery_app
from modules.attendance.application.handlers.attendance_notification_handler import (
    AttendancePushNotificationHandler,
)
from modules.attendance.domain.events.attendance_events import AttendanceSessionClosedEvent
from modules.attendance.infra.repositories.session_sqlalchemy_repository import (
    SessionSQLAlchemyRepository,
)
from modules.enrollment.infra.repositories.enrollment_sqlalchemy_repository import (
    EnrollmentSQLAlchemyRepository,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    name="attendance.close_expired_sessions",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def close_expired_sessions_task(self: Task) -> dict[str, int]:
    """
    Task periódica (Celery Beat) para fechar sessões de chamada que atingiram o tempo limite (expires_at)
    e enviar notificações push de encerramento para os alunos matriculados na turma.
    """


    async def _run() -> int:
        async with AsyncSessionLocal() as session:
            session_repo = SessionSQLAlchemyRepository(session)
            enrollment_repo = EnrollmentSQLAlchemyRepository(session)
            handler = AttendancePushNotificationHandler(enrollment_repo=enrollment_repo)

            closed_sessions = await session_repo.close_expired_sessions()
            for closed_session in closed_sessions:
                subject_class_name = (
                    closed_session.subject_class.name
                    if getattr(closed_session, "subject_class", None)
                    else "Turma"
                )
                event = AttendanceSessionClosedEvent(
                    session_id=closed_session.id,
                    subject_class_id=closed_session.subject_class_id,
                    subject_class_name=subject_class_name,
                )
                await handler.on_session_closed(event)

            return len(closed_sessions)

    try:
        closed_count = asyncio.run(_run())
        logger.info("close_expired_sessions_task: encerradas %d chamadas expiradas.", closed_count)
        return {"closed_count": closed_count}
    except Exception as exc:
        logger.error("close_expired_sessions_task error: %s", exc)
        raise
