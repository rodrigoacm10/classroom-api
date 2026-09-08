import logging
from celery import Task
from firebase_admin import messaging
from firebase_admin.exceptions import FirebaseError

from infra.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# FCM suporta no máximo 500 tokens por chamada de send_each_for_multicast
FCM_MAX_TOKENS_PER_BATCH = 500


def _chunk(lst: list, size: int) -> list[list]:
    """Divide uma lista em sublistas de tamanho máximo `size`."""
    return [lst[i : i + size] for i in range(0, len(lst), size)]


@celery_app.task(
    name="notification.send_push_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(FirebaseError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def send_push_notification(
    self: Task,
    title: str,
    body: str,
    data: dict[str, str],
    fcm_tokens: list[str],
) -> dict[str, int]:
    """
    Task genérica de envio de push notification via Firebase Cloud Messaging.

    Suporta qualquer tipo de notificação do sistema (abertura de chamada, fechamento,
    matrícula aprovada, etc.). O conteúdo (title, body, data) é definido pelo
    handler que despacha a task.

    Args:
        title: Título da notificação exibido no dispositivo.
        body: Corpo da mensagem exibido no dispositivo.
        data: Payload de dados extras acessíveis no app mesmo em background.
        fcm_tokens: Lista de FCM tokens dos destinatários.

    Returns:
        Dicionário com contagem de sucessos e falhas.
    """
    if not fcm_tokens:
        logger.info("send_push_notification: no tokens, skipping.")
        return {"success_count": 0, "failure_count": 0}

    total_success = 0
    total_failure = 0

    for batch in _chunk(fcm_tokens, FCM_MAX_TOKENS_PER_BATCH):
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data=data,
            android=messaging.AndroidConfig(
                priority="high",
                ttl=int(data.get("duration_minutes", "0")) * 60 if "duration_minutes" in data else 3600,
            ),
            apns=messaging.APNSConfig(
                headers={"apns-priority": "10"},
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(title=title, body=body),
                        sound="default",
                        badge=1,
                    )
                ),
            ),
            tokens=batch,
        )

        try:
            response = messaging.send_each_for_multicast(message)
            total_success += response.success_count
            total_failure += response.failure_count

            # Identificar tokens inválidos/desinstalados (UNREGISTERED)
            stale_tokens = []
            for idx, result in enumerate(response.responses):
                if not result.success:
                    error_code = getattr(result.exception, "code", "unknown")
                    logger.warning("FCM delivery failed for token index %d: %s", idx, error_code)
                    if error_code in ("registration-token-not-registered", "invalid-argument", "UNREGISTERED"):
                        stale_tokens.append(batch[idx])

            if stale_tokens:
                logger.info("Identificados %d tokens inativos/desinstalados para remoção.", len(stale_tokens))

        except FirebaseError as exc:
            logger.error("Firebase batch error: %s. Retrying...", exc)
            raise  # autoretry_for captura e re-enfileira

    logger.info(
        "Push notification sent: %d success, %d failure (total: %d tokens)",
        total_success,
        total_failure,
        len(fcm_tokens),
    )
    return {"success_count": total_success, "failure_count": total_failure}
