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

TEMPLATE_PATH = Path(__file__).parent / "templates" / "invite.html"


def _render_template(
    inviter_name: str,
    tenant_name: str,
    role_display: str,
    invite_link: str,
    expires_in_hours: int,
) -> str:
    """Lê e substitui as variáveis no template HTML de convite."""
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template HTML de convite não encontrado em: {TEMPLATE_PATH}")

    content = TEMPLATE_PATH.read_text(encoding="utf-8")
    content = content.replace("{{ inviter_name }}", inviter_name)
    content = content.replace("{{ tenant_name }}", tenant_name)
    content = content.replace("{{ role_display }}", role_display)
    content = content.replace("{{ invite_link }}", invite_link)
    content = content.replace("{{ expires_in_hours }}", str(expires_in_hours))
    return content


def send_invite_email(
    to_email: str,
    tenant_name: str,
    inviter_name: str,
    role: str,
    invite_link: str,
    expires_in_hours: int = 72,
) -> None:
    """Dispara o e-mail de convite para o usuário via Resend utilizando o template HTML."""
    if not settings.resend_api_key:
        logger.warning(
            f"RESEND_API_KEY não configurada. Simulando envio de e-mail de convite para {to_email}. Link: {invite_link}"
        )
        return

    resend.api_key = settings.resend_api_key

    role_display = ROLE_MAP.get(role.lower(), role)

    html_content = _render_template(
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
