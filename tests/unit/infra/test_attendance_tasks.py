from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from infra.tasks.attendance_tasks import close_expired_sessions_task


class TestAttendanceTasks:
    """
    Suíte de Testes: Celery Attendance Tasks (infra/tasks/attendance_tasks.py)
    Valida a execução do job Celery Beat responsável por encerrar chamadas expiradas.
    """

    def test_close_expired_sessions_task_success_unit(self):

        """Deve fechar chamadas vencidas chamando o repositório e despachando os eventos de notificação."""
        mock_session = MagicMock()
        mock_session.id = uuid4()
        mock_session.subject_class_id = uuid4()
        mock_session.subject_class.name = "Álgebra Linear"

        with patch(
            "infra.database.session.AsyncSessionLocal",
            return_value=AsyncMock(),
        ):
            with patch(
                "modules.attendance.infra.repositories.session_sqlalchemy_repository.SessionSQLAlchemyRepository.close_expired_sessions",
                new_callable=AsyncMock,
                return_value=[mock_session],
            ) as mock_close:
                with patch(
                    "modules.attendance.application.handlers.attendance_notification_handler.AttendancePushNotificationHandler.on_session_closed",
                    new_callable=AsyncMock,
                ) as mock_notify:
                    res = close_expired_sessions_task()

                    assert res == {"closed_count": 1}
                    mock_close.assert_called_once()
                    mock_notify.assert_called_once()
