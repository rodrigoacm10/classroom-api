from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.settings import settings

# O engine assíncrono usa o driver psycopg3 (postgresql+psycopg).
# echo=False em produção; pode ser True para depuração local.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout,
    pool_pre_ping=settings.database_pool_pre_ping,
)

# async_sessionmaker é o equivalente assíncrono do sessionmaker.
# expire_on_commit=False evita erros ao acessar atributos após o commit
# dentro de um contexto assíncrono (lazy loading não funciona com async).
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """
    Uma transação por unidade de trabalho: commit se terminar bem, rollback se falhar.
    Evita adquirir conexão do pool para commit/rollback caso nenhuma operação
    tenha iniciado transação na sessão.

    Use em requests HTTP (`get_db`), tasks Celery e qualquer script fora do FastAPI.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            if not isinstance(session, AsyncSession) or session.in_transaction():
                await session.commit()
        except Exception:
            if not isinstance(session, AsyncSession) or session.in_transaction():
                await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency do FastAPI que fornece uma AsyncSession por requisição.

    Uso nos routers:
        db: AsyncSession = Depends(get_db)
    """
    async with session_scope() as session:
        yield session
