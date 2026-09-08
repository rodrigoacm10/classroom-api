from celery import Celery
from celery.signals import worker_process_init

from config.settings import settings

celery_app = Celery(
    "classroom_tasks",
    broker=settings.effective_celery_broker,
    backend=settings.effective_celery_backend,
    include=["infra.tasks.notification_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=4,
)


@worker_process_init.connect
def init_worker(**kwargs: object) -> None:
    """
    Executado uma única vez quando cada processo worker é iniciado.
    Garante que o Firebase SDK esteja inicializado ANTES de qualquer task rodar.
    """
    from infra.firebase.client import init_firebase

    init_firebase()
