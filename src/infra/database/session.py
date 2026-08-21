from collections.abc import AsyncGenerator

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


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency do FastAPI que fornece uma AsyncSession por requisição.

    Uso nos routers:
        db: AsyncSession = Depends(get_db)
    """
    async with AsyncSessionLocal() as session:
        yield session
