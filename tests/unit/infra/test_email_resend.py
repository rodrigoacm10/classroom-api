from unittest.mock import patch

from config.settings import Settings
from infra.email.resend_client import (
    _is_placeholder_api_key,
    send_invite_email,
    send_password_reset_email,
)


class TestEmailSettings:
    """Testes para resolução e montagem dinâmica do remetente de e-mail."""

    def test_default_sender_assembly(self) -> None:
        """Verifica se monta 'Nome <prefixo@dominio>' por padrão."""
        custom_settings = Settings(
            mail_domain="rodrigoacm.com",
            mail_from_prefix="noreply",
            mail_from_name="Classroom",
            email_from="",
        )
        assert custom_settings.email_from == "Classroom <noreply@rodrigoacm.com>"
        assert custom_settings.mail_from_address == "noreply@rodrigoacm.com"

    def test_custom_domain_change(self) -> None:
        """Verifica se trocar o domínio altera dinamicamente o remetente sem alterar código."""
        custom_settings = Settings(
            mail_domain="novodominio.edu.br",
            mail_from_prefix="auth",
            mail_from_name="Minha Escola",
            email_from="",
        )
        assert custom_settings.email_from == "Minha Escola <auth@novodominio.edu.br>"
        assert custom_settings.mail_from_address == "auth@novodominio.edu.br"

    def test_explicit_email_from_override(self) -> None:
        """Quando EMAIL_FROM for explicitamente fornecido, ele deve ter precedência."""
        custom_settings = Settings(
            mail_domain="rodrigoacm.com",
            email_from="Equipe Classroom <suporte@rodrigoacm.com>",
        )
        assert custom_settings.email_from == "Equipe Classroom <suporte@rodrigoacm.com>"

    def test_fallback_when_no_domain(self) -> None:
        """Quando não houver domínio configurado, deve fazer fallback para onboarding@resend.dev."""
        custom_settings = Settings(
            mail_domain="",
            email_from="",
        )
        assert custom_settings.email_from == "onboarding@resend.dev"
        assert custom_settings.mail_from_address == "onboarding@resend.dev"


class TestResendClient:
    """Testes unitários para envio de e-mails via cliente Resend."""

    def test_placeholder_api_key_detection(self) -> None:
        assert _is_placeholder_api_key(None) is True
        assert _is_placeholder_api_key("") is True
        assert _is_placeholder_api_key("   ") is True
        assert _is_placeholder_api_key("change-me") is True
        assert _is_placeholder_api_key("re_123456789") is True
        assert _is_placeholder_api_key("re_xxxx") is True
        assert _is_placeholder_api_key("sample_active_key_example_123") is False

    @patch("infra.email.resend_client.resend.Emails.send")
    @patch("infra.email.resend_client.settings")
    def test_send_invite_email_success(self, mock_settings, mock_send) -> None:
        mock_settings.resend_api_key = "re_valid_key_123"
        mock_settings.email_from = "Classroom <noreply@rodrigoacm.com>"
        mock_send.return_value = {"id": "msg_invite_123"}

        result = send_invite_email(
            to_email="professor@escola.com",
            tenant_name="Escola Aprender",
            inviter_name="Diretor Carlos",
            role="professor",
            invite_link="http://localhost:3000/invites/accept?token=abc",
            expires_in_hours=72,
        )

        assert result == "msg_invite_123"
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        assert payload["from"] == "Classroom <noreply@rodrigoacm.com>"
        assert payload["to"] == ["professor@escola.com"]
        assert "Escola Aprender" in payload["subject"]

    @patch("infra.email.resend_client.resend.Emails.send")
    @patch("infra.email.resend_client.settings")
    def test_send_password_reset_email_success(self, mock_settings, mock_send) -> None:
        mock_settings.resend_api_key = "re_valid_key_123"
        mock_settings.email_from = "Classroom <noreply@rodrigoacm.com>"
        mock_send.return_value = {"id": "msg_reset_456"}

        result = send_password_reset_email(
            to_email="aluno@escola.com",
            user_name="Aluno João",
            code="123456",
            expires_in_minutes=15,
        )

        assert result == "msg_reset_456"
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        assert payload["from"] == "Classroom <noreply@rodrigoacm.com>"
        assert payload["to"] == ["aluno@escola.com"]
        assert "123456" in payload["subject"]

    @patch("infra.email.resend_client.settings")
    def test_simulation_mode_when_placeholder_key(self, mock_settings) -> None:
        mock_settings.resend_api_key = "re_123456789"
        result = send_password_reset_email(
            to_email="test@escola.com",
            user_name="Teste",
            code="654321",
        )
        assert result is None

    @patch("infra.email.resend_client.resend.Emails.send")
    @patch("infra.email.resend_client.settings")
    def test_resend_api_error_handling(self, mock_settings, mock_send) -> None:
        mock_settings.resend_api_key = "re_valid_key"
        mock_settings.email_from = "Classroom <noreply@rodrigoacm.com>"
        mock_send.side_effect = Exception("Domain not verified")

        result = send_password_reset_email(
            to_email="aluno@escola.com",
            user_name="Aluno João",
            code="123456",
        )
        # Não deve estourar erro para o chamador, apenas logar e retornar None
        assert result is None
