from unittest.mock import patch
from uuid import uuid4

import pytest

from modules.attendance.application.handlers.attendance_notification_handler import (
    AttendancePushNotificationHandler,
    register_attendance_event_handlers,
)
from modules.attendance.domain.events.attendance_events import (
    AttendanceSessionClosedEvent,
    AttendanceSessionOpenedEvent,
)
from shared.events.event_dispatcher import EventDispatcher
from tests.unit.fakes.fake_enrollment_repository import FakeEnrollmentRepository


@pytest.mark.asyncio
class TestAttendancePushNotificationHandler:
    """
    Suíte de Testes: AttendancePushNotificationHandler
    Valida o envio de notificações push via Celery em resposta aos eventos de abertura e fechamento de chamadas.
    """

    @pytest.fixture
    def enrollment_repo(self) -> FakeEnrollmentRepository:
        return FakeEnrollmentRepository()

    @pytest.fixture
    def handler(self, enrollment_repo: FakeEnrollmentRepository) -> AttendancePushNotificationHandler:
        return AttendancePushNotificationHandler(enrollment_repo=enrollment_repo)

    async def test_on_session_opened_dispatches_push_when_tokens_exist(
        self, handler: AttendancePushNotificationHandler, enrollment_repo: FakeEnrollmentRepository
    ):
        """Deve disparar notificação push via Celery com título, corpo e payload formatados quando a chamada for aberta."""
        sc_id = uuid4()
        session_id = uuid4()
        enrollment_repo.set_active_fcm_tokens(sc_id, ["token_mobile_1", "token_tablet_2"])

        event = AttendanceSessionOpenedEvent(
            session_id=session_id,
            subject_class_id=sc_id,
            subject_class_name="Cálculo I",
            day_code="CALC123",
            duration_minutes=20,
        )

        with patch("infra.tasks.notification_tasks.send_push_notification.delay") as mock_delay:
            await handler.on_session_opened(event)

            mock_delay.assert_called_once_with(
                title="📋 Chamada Aberta — Cálculo I",
                body="O professor iniciou a chamada! Você tem 20 minutos. Código: CALC123",
                data={
                    "type": "ATTENDANCE_OPENED",
                    "day_code": "CALC123",
                    "subject_class_name": "Cálculo I",
                    "duration_minutes": "20",
                },
                fcm_tokens=["token_mobile_1", "token_tablet_2"],
            )

    async def test_on_session_opened_skips_when_no_tokens(
        self, handler: AttendancePushNotificationHandler, enrollment_repo: FakeEnrollmentRepository
    ):
        """Deve ignorar o envio da task Celery sem lançar erros caso nenhum aluno da turma possua token FCM cadastrado."""
        sc_id = uuid4()
        enrollment_repo.set_active_fcm_tokens(sc_id, [])

        event = AttendanceSessionOpenedEvent(
            session_id=uuid4(),
            subject_class_id=sc_id,
            subject_class_name="Álgebra Linear",
            day_code="ALG999",
            duration_minutes=15,
        )

        with patch("infra.tasks.notification_tasks.send_push_notification.delay") as mock_delay:
            await handler.on_session_opened(event)
            mock_delay.assert_not_called()

    async def test_on_session_closed_dispatches_push_when_tokens_exist(
        self, handler: AttendancePushNotificationHandler, enrollment_repo: FakeEnrollmentRepository
    ):
        """Deve disparar notificação push via Celery avisando os alunos sobre o encerramento da chamada."""
        sc_id = uuid4()
        enrollment_repo.set_active_fcm_tokens(sc_id, ["token_mobile_1"])

        event = AttendanceSessionClosedEvent(
            session_id=uuid4(),
            subject_class_id=sc_id,
            subject_class_name="Física III",
        )

        with patch("infra.tasks.notification_tasks.send_push_notification.delay") as mock_delay:
            await handler.on_session_closed(event)

            mock_delay.assert_called_once_with(
                title="🔒 Chamada Encerrada — Física III",
                body="A janela de confirmação de presença foi encerrada pelo professor.",
                data={
                    "type": "ATTENDANCE_CLOSED",
                    "subject_class_name": "Física III",
                },
                fcm_tokens=["token_mobile_1"],
            )

    async def test_on_session_closed_skips_when_no_tokens(
        self, handler: AttendancePushNotificationHandler, enrollment_repo: FakeEnrollmentRepository
    ):
        """Deve ignorar o envio da task Celery ao encerrar chamada caso não existam tokens ativos na turma."""
        sc_id = uuid4()
        enrollment_repo.set_active_fcm_tokens(sc_id, [])

        event = AttendanceSessionClosedEvent(
            session_id=uuid4(),
            subject_class_id=sc_id,
            subject_class_name="Química Geral",
        )

        with patch("infra.tasks.notification_tasks.send_push_notification.delay") as mock_delay:
            await handler.on_session_closed(event)
            mock_delay.assert_not_called()

    async def test_register_attendance_event_handlers_registers_listeners(self):
        """Deve registrar os ouvintes (listeners) dos eventos AttendanceSessionOpenedEvent e AttendanceSessionClosedEvent no barramento EventDispatcher."""
        dispatcher = EventDispatcher()
        register_attendance_event_handlers(dispatcher)

        listeners_opened = dispatcher._handlers.get(AttendanceSessionOpenedEvent, [])
        listeners_closed = dispatcher._handlers.get(AttendanceSessionClosedEvent, [])

        assert len(listeners_opened) == 1
        assert len(listeners_closed) == 1
