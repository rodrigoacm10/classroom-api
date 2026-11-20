"""Sobe a API HTTP. Ponto de entrada do executável, sem regra de negócio."""

import multiprocessing
import os

import celery.backends.redis as celery_redis_backend
import celery.fixups.django as celery_django_fixup
import celery.loaders.app as celery_app_loader
import kombu.transport.redis as kombu_redis
import pwdlib.hashers.argon2 as argon2_hasher
import sqlalchemy.dialects.postgresql.psycopg as sa_psycopg_dialect
import uvicorn

from main import app

# O Celery, o SQLAlchemy e o pwdlib carregam estes módulos pelo nome.
_RUNTIME_MODULES = (
    celery_redis_backend,
    celery_django_fixup,
    celery_app_loader,
    kombu_redis,
    argon2_hasher,
    sa_psycopg_dialect,
)


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
