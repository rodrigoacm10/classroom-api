from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

from config.settings import settings
from infra.database.base import Base
# import infra.database.models  # noqa: F401 — garante que todos os models sejam registrados no metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Alembic usa engine síncrono mesmo que a aplicação use AsyncEngine.
    # Isso é intencional: migrations rodam como scripts CLI, não como handlers HTTP.
    connectable = create_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
