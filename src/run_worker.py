"""Sobe o worker Celery e o agendador. Ponto de entrada do executável, sem regra de negócio."""

import multiprocessing
import sys

import celery.app.amqp as celery_app_amqp
import celery.app.control as celery_app_control
import celery.app.events as celery_app_events
import celery.app.log as celery_app_log
import celery.apps.beat as celery_apps_beat
import celery.apps.worker as celery_apps_worker
import celery.backends.redis as celery_redis_backend
import celery.beat as celery_beat
import celery.concurrency.prefork as celery_prefork
import celery.events.dispatcher as celery_events_dispatcher
import celery.events.receiver as celery_events_receiver
import celery.events.state as celery_events_state
import celery.fixups.django as celery_django_fixup
import celery.loaders.app as celery_app_loader
import celery.result as celery_result
import celery.worker.autoscale as celery_worker_autoscale
import celery.worker.components as celery_worker_components
import celery.worker.consumer as celery_worker_consumer
import celery.worker.consumer.delayed_delivery as celery_delayed_delivery
import celery.worker.request as celery_worker_request
import celery.worker.strategy as celery_worker_strategy
import kombu.transport.redis as kombu_redis
import pwdlib.hashers.argon2 as argon2_hasher
import sqlalchemy.dialects.postgresql.psycopg as sa_psycopg_dialect

import infra.tasks.attendance_tasks as attendance_tasks
import infra.tasks.email_tasks as email_tasks
import infra.tasks.notification_tasks as notification_tasks
from infra.tasks.celery_app import celery_app

# Tasks e módulos que o Celery resolve por string na subida do worker.
_TASK_MODULES = (
    attendance_tasks,
    email_tasks,
    notification_tasks,
    celery_app_amqp,
    celery_app_control,
    celery_app_events,
    celery_app_log,
    celery_apps_beat,
    celery_apps_worker,
    celery_redis_backend,
    celery_beat,
    celery_prefork,
    celery_events_dispatcher,
    celery_events_receiver,
    celery_events_state,
    celery_result,
    celery_django_fixup,
    celery_app_loader,
    celery_worker_autoscale,
    celery_worker_components,
    celery_worker_consumer,
    celery_delayed_delivery,
    celery_worker_request,
    celery_worker_strategy,
    kombu_redis,
    argon2_hasher,
    sa_psycopg_dialect,
)


def main() -> None:
    extra = sys.argv[1:]
    if not extra:
        extra = ["-B", "--loglevel=info"]
    argv = extra if "worker" in extra else ["worker", *extra]
    celery_app.worker_main(argv=argv)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
