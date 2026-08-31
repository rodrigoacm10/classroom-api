import logging
from pathlib import Path

import resend

from config.settings import settings

logger = logging.getLogger(__name__)

ROLE_MAP = {
    "admin": "Administrador",
    "professor": "Professor",
    "aluno": "Aluno",
    "coordenador": "Coordenador",
}

TEMPLATES_DIR = Path(__file__).parent / "templates"
INVITE_TEMPLATE_PATH = TEMPLATES_DIR / "invite.html"
PASSWORD_RESET_TEMPLATE_PATH = TEMPLATES_DIR / "password_reset.html"


def _is_placeholder_api_key(api_key: str | None) -> bool:
    """Verifica se a chave da API é nula, vazia ou um valor fictício de template."""
    if not api_key:
        return True
    key = api_key.strip()
    return (
        key == ""
        or key == "change-me"
        or key.startswith("re_123456789")
        or key.startswith("re_xxxx")
    )


def _render_invite_template(
    inviter_name: str,
    tenant_name: str,
    role_display: str,
    invite_link: str,
    expires_in_hours: int,
) -> str:
    """Lê e substitui as variáveis no template HTML de convite."""
    if not INVITE_TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template HTML de convite não encontrado em: {INVITE_TEMPLATE_PATH}")

    content = INVITE_TEMPLATE_PATH.read_text(encoding="utf-8")
    content = content.replace("{{ inviter_name }}", inviter_name)
    content = content.replace("{{ tenant_name }}", tenant_name)
    content = content.replace("{{ role_display }}", role_display)
    content = content.replace("{{ invite_link }}", invite_link)
    content = content.replace("{{ expires_in_hours }}", str(expires_in_hours))
    return content


def _render_password_reset_template(
    user_name: str,
    code: str,
    expires_in_minutes: int,
) -> str:
    """Lê e substitui as variáveis no template HTML de recuperação de senha."""
    if not PASSWORD_RESET_TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"Template HTML de recuperação de senha não encontrado em: {PASSWORD_RESET_TEMPLATE_PATH}"
        )

    content = PASSWORD_RESET_TEMPLATE_PATH.read_text(encoding="utf-8")
    content = content.replace("{{ user_name }}", user_name)
    content = content.replace("{{ code }}", code)
    content = content.replace("{{ expires_in_minutes }}", str(expires_in_minutes))
    return content


def send_invite_email(
    to_email: str,
    tenant_name: str,
    inviter_name: str,
    role: str,
    invite_link: str,
    expires_in_hours: int = 72,
) -> None:
    """
    Dispara o e-mail de convite para o usuário via Resend utilizando o template HTML.
    Em desenvolvimento (ou sem chave configurada), simula o envio via log sem lançar exceção.
    """
    if _is_placeholder_api_key(settings.resend_api_key):
        logger.warning(
            f"[EMAIL SIMULATION] RESEND_API_KEY não configurada ou placeholder. "
            f"Convite para: {to_email} | Instituição: {tenant_name} | Papel: {role} | Link: {invite_link}"
        )
        return

    resend.api_key = settings.resend_api_key

    try:
        role_display = ROLE_MAP.get(role.lower(), role)

        html_content = _render_invite_template(
            inviter_name=inviter_name,
            tenant_name=tenant_name,
            role_display=role_display,
            invite_link=invite_link,
            expires_in_hours=expires_in_hours,
        )

        resend.Emails.send({
            "from": settings.email_from,
            "to": [to_email],
            "subject": f"Você foi convidado para participar de {tenant_name}",
            "html": html_content,
        })
    except Exception as exc:
        logger.error(
            f"Erro ao disparar e-mail de convite para {to_email} via Resend: {exc}. "
            f"Link de convite: {invite_link}"
        )


def send_password_reset_email(
    to_email: str,
    user_name: str,
    code: str,
    expires_in_minutes: int = 15,
) -> None:
    """
    Dispara o e-mail com código OTP de recuperação de senha via Resend.
    Em desenvolvimento (ou sem chave configurada), simula o envio via log com o código OTP.
    """
    if _is_placeholder_api_key(settings.resend_api_key):
        logger.warning(
            f"[EMAIL SIMULATION] RESEND_API_KEY não configurada ou placeholder. "
            f"Recuperação de senha para: {to_email} ({user_name}) | Código OTP: {code} | Expira em: {expires_in_minutes} min"
        )
        return

    resend.api_key = settings.resend_api_key

    try:
        html_content = _render_password_reset_template(
            user_name=user_name,
            code=code,
            expires_in_minutes=expires_in_minutes,
        )

        resend.Emails.send({
            "from": settings.email_from,
            "to": [to_email],
            "subject": f"Código de recuperação de senha: {code}",
            "html": html_content,
        })
    except Exception as exc:
        logger.error(
            f"Erro ao disparar e-mail de recuperação de senha para {to_email} via Resend: {exc}. "
            f"Código OTP gerado: {code}"
        )
