"""
Fixtures de infraestrutura para testes E2E.

Estratégia de isolamento:
- `engine` (scope=session):       1 engine para toda a sessão de testes E2E.
- `create_tables` (scope=session): cria tabelas antes, dropa ao final.
- `session` (scope=function):     1 transação por teste → rollback automático.
- `client` (scope=function):      AsyncClient com overrides:
    * `get_db`           → retorna a sessão do banco de testes (mesma transação).
    * `app.state.limiter`→ limiter em memória fresco para evitar 429 nos testes.

O `client` captura a `session` no closure de `override_get_db`, de modo que tanto
o código do teste quanto o handler FastAPI usam o MESMO objeto de sessão.
Quando o handler faz `session.commit()` internamente, ele comita um SAVEPOINT
(não a transação externa), então o `rollback()` ao final do teste desfaz tudo.
"""
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sqlalchemy import text

TEST_DATABASE_URL = (
    "postgresql+psycopg://classroom:classroom@localhost:5432/classroom_test"
)


@pytest.fixture(scope="session")
def engine():
    """Engine assíncrono compartilhado pela sessão de testes E2E."""
    return create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest.fixture(scope="session")
async def create_tables(engine) -> AsyncGenerator[None, None]:
    """Cria as tabelas no banco de testes antes dos testes E2E e dropa ao final."""
    import infra.database.models  # noqa: F401 — side-effect import
    from infra.database.base import Base

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        await conn.run_sync(Base.metadata.create_all)

    yield


    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def session(engine, create_tables) -> AsyncGenerator[AsyncSession, None]:
    """
    Sessão de banco de dados com rollback automático por teste.

    É compartilhada com a aplicação FastAPI via `override_get_db` na fixture
    `client`. Isso garante que os dados criados na fase de setup do teste sejam
    visíveis para os handlers HTTP sem precisar de um commit real.
    """
    async with engine.connect() as conn:
        await conn.begin()
        session_factory = async_sessionmaker(
            bind=conn,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        async with session_factory() as sess:
            yield sess
            await sess.rollback()


@pytest.fixture
async def client(session) -> AsyncGenerator[AsyncClient, None]:
    """
    AsyncClient configurado para disparar requisições HTTP reais à app FastAPI
    em memória (sem precisar de um servidor uvicorn rodando).

    Overrides aplicados durante o escopo deste fixture:
    - `get_db`: substituído por `override_get_db` que retorna a sessão do banco
      de testes — o mesmo objeto que o teste usa para criar dados.
    - `limiter.enabled = False`: desabilita o rate limiter do slowapi via o
      atributo oficial — `_check_request_limit` retorna imediatamente quando
      `self.enabled` é False, sem tocar no Redis.
    """
    from infra.database.session import get_db
    from main import app
    from security.rate_limiter import limiter

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        """Injeta a sessão de teste no lugar da sessão de produção."""
        yield session

    app.dependency_overrides[get_db] = override_get_db

    # Desabilita o rate limiter via atributo oficial do slowapi.
    # `_check_request_limit` checa `self.enabled` como primeira condição
    # e retorna sem verificar limites quando é False.
    limiter.enabled = False
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
    finally:
        limiter.enabled = True
        app.dependency_overrides.pop(get_db, None)
        from infra.cache.redis_client import redis_client
        await redis_client.connection_pool.disconnect()
