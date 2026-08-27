"""
Fixtures de infraestrutura para testes de integração.

Estratégia de isolamento:
- `engine` (scope=session):     1 engine para toda a sessão de testes
- `create_tables` (scope=session): cria as tabelas antes e dropa depois
- `session` (scope=function):   1 transação por teste → rollback automático ao final

O rollback automático garante que cada teste começa com o banco limpo,
sem precisar truncar tabelas ou recriar o banco entre testes.
"""
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Banco de dados EXCLUSIVO para testes — nunca toca o banco de desenvolvimento
TEST_DATABASE_URL = (
    "postgresql+psycopg://classroom:classroom@localhost:5432/classroom_test"
)


@pytest.fixture(scope="session")
def engine():
    """Cria um único engine assíncrono compartilhado pela sessão de testes inteira."""
    return create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest.fixture(scope="session")
async def create_tables(engine) -> AsyncGenerator[None, None]:
    """
    Cria todas as tabelas no banco de testes antes de qualquer teste rodar.
    Dropa todas as tabelas ao final da sessão.

    Importar os models aqui é necessário para que o SQLAlchemy saiba quais
    tabelas fazem parte do metadata de Base.
    """
    # Importação garante que os models sejam registrados no Base.metadata
    import infra.database.models  # noqa: F401 — side-effect import
    from infra.database.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield  # Testes de integração rodam aqui

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def session(engine, create_tables) -> AsyncGenerator[AsyncSession, None]:
    """
    Fornece uma AsyncSession que faz ROLLBACK automático ao final do teste.

    Funciona assim:
    1. Abre uma conexão e inicia uma transação.
    2. Cria uma Session vinculada a essa conexão (não ao engine).
    3. Yield: o teste executa com acesso ao banco real.
    4. Rollback: desfaz TUDO que o teste escreveu, sem precisar limpar manualmente.

    Isso é muito mais rápido do que dropar/recriar tabelas entre cada teste.
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
