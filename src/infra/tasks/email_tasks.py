import logging

from celery import Task

from infra.email.resend_client import send_invite_email, send_password_reset_email
from infra.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="email.send_invite_email",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def send_invite_email_task(
    self: Task,
    to_email: str,
    tenant_name: str,
    inviter_name: str,
    role: str,
    invite_link: str,
    expires_in_hours: int = 72,
) -> str | None:
    """
    Task Celery de envio assíncrono de e-mail de convite via Resend.
    Executada fora do ciclo HTTP da API com retry exponencial automático em caso de falha de rede/API.
    """
    return send_invite_email(
        to_email=to_email,
        tenant_name=tenant_name,
        inviter_name=inviter_name,
        role=role,
        invite_link=invite_link,
        expires_in_hours=expires_in_hours,
        raise_on_error=True,
    )


@celery_app.task(
    name="email.send_password_reset_email",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def send_password_reset_email_task(
    self: Task,
    to_email: str,
    user_name: str,
    code: str,
    expires_in_minutes: int = 15,
) -> str | None:
    """
    Task Celery de envio assíncrono de e-mail de recuperação de senha (OTP) via Resend.
    Executada fora do ciclo HTTP da API com retry exponencial automático em caso de falha de rede/API.
    """
    return send_password_reset_email(
        to_email=to_email,
        user_name=user_name,
        code=code,
        expires_in_minutes=expires_in_minutes,
        raise_on_error=True,
    )
