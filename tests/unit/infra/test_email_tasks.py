from unittest.mock import patch

import pytest

from infra.tasks.celery_app import celery_app
from infra.tasks.email_tasks import (
    send_invite_email_task,
    send_password_reset_email_task,
)


class TestEmailTasks:
    """
    Suíte de Testes: Celery Email Tasks (infra/tasks/email_tasks.py)
    Valida o registro no Celery e o disparo assíncrono de e-mails de convite e recuperação de senha.
    """

    def test_email_tasks_registered_in_celery_include(self) -> None:
        assert "infra.tasks.email_tasks" in celery_app.conf.include
        assert send_invite_email_task.name == "email.send_invite_email"
        assert send_password_reset_email_task.name == "email.send_password_reset_email"
        assert send_invite_email_task.max_retries == 3
        assert send_password_reset_email_task.max_retries == 3

    @patch("infra.tasks.email_tasks.send_invite_email", return_value="msg_invite_999")
    def test_send_invite_email_task_delegates_with_raise_on_error(self, mock_send_invite) -> None:
        result = send_invite_email_task(
            to_email="professor@escola.com",
            tenant_name="Escola Alfa",
            inviter_name="Diretor",
            role="professor",
            invite_link="https://classroom.app/invites/accept?token=xyz",
            expires_in_hours=72,
        )

        assert result == "msg_invite_999"
        mock_send_invite.assert_called_once_with(
            to_email="professor@escola.com",
            tenant_name="Escola Alfa",
            inviter_name="Diretor",
            role="professor",
            invite_link="https://classroom.app/invites/accept?token=xyz",
            expires_in_hours=72,
            raise_on_error=True,
        )

    @patch("infra.tasks.email_tasks.send_password_reset_email", return_value="msg_reset_888")
    def test_send_password_reset_email_task_delegates_with_raise_on_error(
        self, mock_send_reset
    ) -> None:
        result = send_password_reset_email_task(
            to_email="aluno@escola.com",
            user_name="Aluno",
            code="654321",
            expires_in_minutes=15,
        )

        assert result == "msg_reset_888"
        mock_send_reset.assert_called_once_with(
            to_email="aluno@escola.com",
            user_name="Aluno",
            code="654321",
            expires_in_minutes=15,
            raise_on_error=True,
        )

    @patch(
        "infra.tasks.email_tasks.send_password_reset_email",
        side_effect=ConnectionError("Resend timeout"),
    )
    def test_send_password_reset_email_task_propagates_error_for_celery_autoretry(
        self, mock_send_reset
    ) -> None:
        with pytest.raises(ConnectionError, match="Resend timeout"):
            send_password_reset_email_task(
                to_email="aluno@escola.com",
                user_name="Aluno",
                code="654321",
                expires_in_minutes=15,
            )
