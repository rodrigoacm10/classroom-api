# Testing Guide — Boas Práticas

## Stack de Testes

**Pytest · pytest-asyncio · httpx · Factory Pattern**

```text
pytest >= 9.1.1
pytest-asyncio >= 1.4.0
httpx >= 0.28.1
```

> As dependências de teste vivem no grupo `dev` do `pyproject.toml`. Nunca adicione dependências de teste ao grupo principal.

---

## Estrutura de Diretórios

```text
tests/
├── conftest.py                  # fixtures globais (session, client, factories)
│
├── factories/                   # fábricas de objetos de domínio e modelos
│   ├── __init__.py
│   ├── user_factory.py
│   ├── tenant_factory.py
│   └── appointment_factory.py
│
├── unit/                        # testa lógica isolada, zero I/O
│   ├── conftest.py
│   └── modules/
│       ├── auth/
│       │   └── test_logout_use_case.py
│       └── appointment/
│           └── test_create_appointment_use_case.py
│
├── integration/                 # testa camadas integradas (DB, Redis)
│   ├── conftest.py
│   └── modules/
│       ├── auth/
│       │   └── test_auth_repository.py
│       └── appointment/
│           └── test_appointment_repository.py
│
└── e2e/                         # testa a API completa via HTTP
    ├── conftest.py
    └── modules/
        ├── auth/
        │   └── test_auth_routes.py
        └── appointment/
            └── test_appointment_routes.py
```

A estrutura de `tests/` espelha a estrutura de `src/modules/`. Isso facilita localizar o teste correspondente a qualquer arquivo de produção.

---

## A Pirâmide de Testes

```text
        /\
       /e2e\          ← poucos, lentos, alto custo
      /──────\
     /integra-\
    / tion     \      ← médios, dependem de infra
   /────────────\
  /    unit      \    ← muitos, rápidos, sem I/O
 /────────────────\
```

Regra prática:

- **Unit:** Para toda lógica de domínio e use cases.
- **Integration:** Para repositórios, queries e comportamento com banco de dados real.
- **E2E:** Para fluxos críticos do ponto de vista do cliente HTTP.

---

## Factories

Factories eliminam a repetição de criação de objetos de teste e tornam os testes mais legíveis. Elas centralizam os valores padrão e permitem customização pontual por teste.

### Princípio

```text
Factory → cria objetos com valores sensatos por padrão
Teste   → sobrescreve apenas o que é relevante para o cenário
```

### Estrutura de uma Factory

```python
# tests/factories/user_factory.py

import uuid
from src.modules.user.domain.entities.user import User


class UserFactory:
    """Factory para criar entidades User com valores padrão."""

    @staticmethod
    def make(**overrides) -> User:
        """
        Cria uma entidade User com valores padrão.
        Qualquer campo pode ser sobrescrito via kwargs.
        """
        defaults = {
            "id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "name": "John Doe",
            "email": "john@example.com",
            "hashed_password": "hashed_secret",
            "role": "PROFESSIONAL",
            "is_active": True,
        }
        return User(**{**defaults, **overrides})

    @staticmethod
    def make_admin(**overrides) -> User:
        """Atalho para criar um User com role de admin."""
        return UserFactory.make(role="ADMIN", **overrides)

    @staticmethod
    def make_inactive(**overrides) -> User:
        """Atalho para criar um User inativo."""
        return UserFactory.make(is_active=False, **overrides)
```

### Factory para Modelos SQLAlchemy (Integration / E2E)

Para testes de integração, as factories também podem persistir no banco:

```python
# tests/factories/user_factory.py (seção de persistência)

from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.user.infra.models.user_model import UserModel


class UserFactory:
    ...

    @staticmethod
    async def create(session: AsyncSession, **overrides) -> UserModel:
        """
        Cria e persiste um UserModel no banco de dados.
        Use apenas em testes de integração e e2e.
        """
        defaults = {
            "id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "name": "John Doe",
            "email": f"john_{uuid.uuid4().hex[:6]}@example.com",
            "hashed_password": "hashed_secret",
            "role": "PROFESSIONAL",
            "is_active": True,
        }
        data = {**defaults, **overrides}
        model = UserModel(**data)
        session.add(model)
        await session.commit()
        await session.refresh(model)
        return model
```

> **Atenção:** emails devem ser únicos por padrão. Use `uuid.uuid4().hex[:6]` ou similar nos campos que possuem constraint `UNIQUE` no banco.

---

## Testes Unitários

### Responsabilidade

Testes unitários validam **lógica pura**:

- Entidades de domínio
- Value Objects
- Domain Services
- Use Cases (com repositórios substituídos por fakes/mocks)

### Regras

- Zero I/O: sem banco, sem HTTP, sem Redis
- Sem `pytest-asyncio` obrigatório quando não há `async`
- Nunca mockar o que você possui (entidades e domain services são seus — instancie-os diretamente)
- Mockar apenas o que você **não** possui: repositórios, serviços externos

### Fake Repository

Fakes são implementações em memória de repositórios, usados exclusivamente em testes unitários:

```python
# tests/unit/fakes/fake_user_repository.py

from src.modules.user.domain.entities.user import User
from src.modules.user.domain.repositories.user_repository import UserRepository


class FakeUserRepository:
    """
    Implementação em memória do UserRepository.
    Satisfaz o Protocol sem tocar em banco de dados.
    """

    def __init__(self):
        self._store: dict[str, User] = {}

    async def find_by_email(self, email: str, tenant_id: str) -> User | None:
        return next(
            (u for u in self._store.values()
             if u.email == email and u.tenant_id == tenant_id),
            None,
        )

    async def find_by_id(self, user_id: str, tenant_id: str) -> User | None:
        return self._store.get(user_id)

    async def save(self, user: User) -> User:
        self._store[user.id] = user
        return user
```

### Exemplo — Use Case

```python
# tests/unit/modules/auth/test_logout_use_case.py

import pytest
from tests.factories.user_factory import UserFactory
from tests.unit.fakes.fake_token_blacklist_service import FakeTokenBlacklistService
from src.modules.auth.application.use_cases.logout import LogoutUseCase
from src.modules.auth.domain.exceptions import InvalidTokenException


class TestLogoutUseCase:

    def setup_method(self):
        self.blacklist = FakeTokenBlacklistService()
        self.use_case = LogoutUseCase(token_blacklist=self.blacklist)

    async def test_logout_blacklists_token(self):
        user = UserFactory.make()
        token = "valid.jwt.token"

        await self.use_case.execute(user_id=user.id, token=token)

        assert self.blacklist.contains(token)

    async def test_logout_with_already_blacklisted_token_raises(self):
        token = "already.blacklisted.token"
        await self.blacklist.add(token)

        with pytest.raises(InvalidTokenException):
            await self.use_case.execute(user_id="any-id", token=token)
```

### Exemplo — Entidade de Domínio

```python
# tests/unit/modules/appointment/test_appointment_entity.py

import pytest
from datetime import datetime, timedelta
from tests.factories.appointment_factory import AppointmentFactory


class TestAppointmentEntity:

    def test_appointment_duration_is_calculated_correctly(self):
        now = datetime(2024, 1, 10, 9, 0)
        appointment = AppointmentFactory.make(
            starts_at=now,
            ends_at=now + timedelta(hours=1),
        )

        assert appointment.duration_minutes == 60

    def test_appointment_cannot_be_cancelled_when_already_cancelled(self):
        appointment = AppointmentFactory.make(status="CANCELLED")

        with pytest.raises(ValueError, match="already cancelled"):
            appointment.cancel()

    def test_appointment_in_the_past_cannot_be_rescheduled(self):
        past = datetime(2020, 1, 1)
        appointment = AppointmentFactory.make(starts_at=past)

        with pytest.raises(ValueError):
            appointment.reschedule(new_starts_at=datetime(2020, 1, 2))
```

---

## Testes de Integração

### Responsabilidade

Testes de integração validam a **colaboração entre camadas concretas**:

- Repositório SQLAlchemy contra banco de dados real
- Queries, filtros, constraints e transações
- Comportamento de mappers

### Regras

- Usam um banco de dados de **teste dedicado** (nunca o banco de desenvolvimento ou produção)
- Cada teste recebe uma transação que é **revertida ao final** (ou o banco é limpo via fixture)
- Nunca testam lógica de negócio: isso é responsabilidade dos testes unitários

### `conftest.py` de Integração

```python
# tests/integration/conftest.py

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

TEST_DATABASE_URL = "postgresql+psycopg://user:pass@localhost:5432/classroom_test"


@pytest.fixture(scope="session")
def engine():
    return create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest.fixture(scope="session")
async def create_tables(engine):
    """Cria as tabelas antes de todos os testes da sessão."""
    from src.infra.database.base import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def session(engine, create_tables) -> AsyncSession:
    """
    Fornece uma sessão que faz rollback automático ao final do teste.
    Isso garante isolamento entre os testes sem precisar limpar o banco.
    """
    async with engine.connect() as conn:
        await conn.begin()
        session_factory = async_sessionmaker(bind=conn, expire_on_commit=False)
        async with session_factory() as session:
            yield session
            await session.rollback()
```

### Exemplo — Repositório

```python
# tests/integration/modules/auth/test_auth_repository.py

import pytest
from tests.factories.user_factory import UserFactory
from src.modules.user.infra.repositories.user_sqlalchemy_repository import (
    UserSQLAlchemyRepository,
)


class TestUserSQLAlchemyRepository:

    @pytest.fixture(autouse=True)
    def setup(self, session):
        self.repository = UserSQLAlchemyRepository(session=session)
        self.session = session

    async def test_find_by_email_returns_user_when_exists(self):
        user_model = await UserFactory.create(
            self.session,
            email="jane@example.com",
        )

        result = await self.repository.find_by_email(
            email="jane@example.com",
            tenant_id=user_model.tenant_id,
        )

        assert result is not None
        assert result.email == "jane@example.com"

    async def test_find_by_email_returns_none_for_wrong_tenant(self):
        user_model = await UserFactory.create(
            self.session,
            email="jane@example.com",
        )

        result = await self.repository.find_by_email(
            email="jane@example.com",
            tenant_id="different-tenant-id",   # tenant errado
        )

        assert result is None  # multi-tenant isolamento garantido

    async def test_save_persists_user(self):
        user = UserFactory.make()

        saved = await self.repository.save(user)

        assert saved.id == user.id
        assert saved.email == user.email
```

> O teste `test_find_by_email_returns_none_for_wrong_tenant` é **obrigatório** para todo repositório que lida com dados de tenant. Essa é uma consequência direta da **Multi-Tenant Rule** definida na arquitetura.

---

## Testes E2E

### Responsabilidade

Testes E2E validam **fluxos completos de ponta a ponta** via HTTP:

- Request → Middleware → Auth → Router → Use Case → Repository → DB → Response
- São os testes mais próximos do comportamento real do cliente

### Regras

- Usam o `AsyncClient` do `httpx` (nunca o `TestClient` síncrono para rotas assíncronas)
- Testam os contratos de API: status codes, formato de resposta, headers
- Não testam lógica de negócio: isso é trabalho dos testes unitários
- Foco em cenários críticos de negócio, não em cobertura exaustiva

### `conftest.py` E2E

```python
# tests/e2e/conftest.py

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from main import app
from src.infra.database.session import get_db

TEST_DATABASE_URL = "postgresql+psycopg://user:pass@localhost:5432/classroom_test"


@pytest.fixture(scope="session")
def engine():
    return create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest.fixture
async def session(engine) -> AsyncSession:
    async with engine.connect() as conn:
        await conn.begin()
        factory = async_sessionmaker(bind=conn, expire_on_commit=False)
        async with factory() as sess:
            yield sess
            await sess.rollback()


@pytest.fixture
async def client(session: AsyncSession) -> AsyncClient:
    """
    Cria um AsyncClient com a sessão de teste injetada via dependency override.
    Isso garante que a aplicação use a mesma transação que será revertida.
    """

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
```

### Exemplo — Rota de Autenticação

```python
# tests/e2e/modules/auth/test_auth_routes.py

import pytest
from httpx import AsyncClient
from tests.factories.user_factory import UserFactory


class TestLoginRoute:

    async def test_login_returns_tokens_on_valid_credentials(
        self,
        client: AsyncClient,
        session,
    ):
        await UserFactory.create(
            session,
            email="valid@example.com",
            hashed_password="<hashed_known_password>",
        )

        response = await client.post("/auth/login", json={
            "email": "valid@example.com",
            "password": "known_password",
        })

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert "refresh_token" in body

    async def test_login_returns_401_on_wrong_password(
        self,
        client: AsyncClient,
        session,
    ):
        await UserFactory.create(session, email="user@example.com")

        response = await client.post("/auth/login", json={
            "email": "user@example.com",
            "password": "wrong_password",
        })

        assert response.status_code == 401

    async def test_login_returns_422_when_email_is_missing(
        self,
        client: AsyncClient,
    ):
        response = await client.post("/auth/login", json={
            "password": "some_password",
        })

        assert response.status_code == 422


class TestLogoutRoute:

    async def test_logout_returns_204_with_valid_token(
        self,
        client: AsyncClient,
        session,
    ):
        await UserFactory.create(session, email="user@example.com")
        login = await client.post("/auth/login", json={
            "email": "user@example.com",
            "password": "known_password",
        })
        token = login.json()["access_token"]

        response = await client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 204

    async def test_logout_returns_401_without_token(
        self,
        client: AsyncClient,
    ):
        response = await client.post("/auth/logout")

        assert response.status_code == 401
```

---

## Conftest Global

```python
# tests/conftest.py

import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    """Garante que pytest-asyncio use asyncio como backend."""
    return "asyncio"
```

O `pyproject.toml` já define:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
asyncio_mode = "auto"
```

Com `asyncio_mode = "auto"`, todas as funções `async def test_*` são tratadas como testes assíncronos automaticamente. Não é necessário usar o decorator `@pytest.mark.asyncio`.

---

## Regras Gerais

### 1. Um teste, uma asserção principal

Cada teste deve verificar **um único comportamento**. Múltiplas asserções são aceitáveis quando validam a mesma coisa de ângulos diferentes (ex: status code + corpo da resposta).

❌:
```python
async def test_create_user():
    # verifica criação E email duplicado E autenticação no mesmo teste
    ...
```

✅:
```python
async def test_create_user_returns_created_user(): ...
async def test_create_user_raises_when_email_is_duplicate(): ...
```

---

### 2. Nomes de teste descrevem comportamento

```text
test_<unidade>_<cenário>_<resultado_esperado>
```

Exemplos:

```text
test_logout_with_invalid_token_raises_exception
test_find_by_email_returns_none_when_user_does_not_exist
test_login_returns_401_on_wrong_password
```

---

### 3. Factories, não fixtures para dados de domínio

Use fixtures para **infraestrutura** (sessão, client, engine) e factories para **dados**:

❌:
```python
@pytest.fixture
def user():
    return User(id="1", email="a@b.com", ...)
```

✅:
```python
user = UserFactory.make(email="a@b.com")
```

Factories são mais flexíveis, reutilizáveis entre arquivos e não introduzem acoplamento implícito via fixture.

---

### 4. Testes unitários nunca tocam em infra

Se o seu teste de use case precisa de uma sessão de banco de dados, ele é um teste de integração disfarcado.

```text
Unit Test
    ↓
FakeRepository (in-memory)
    ↓
Domain Entity
```

```text
Integration Test
    ↓
SQLAlchemyRepository (real)
    ↓
PostgreSQL (test database)
```

---

### 5. Isolamento entre testes

Cada teste deve ser independente. A ordem de execução nunca deve importar.

- Use **rollback por transação** no conftest de integração e e2e
- Factories com campos únicos gerados via `uuid4()` previnem colisão de dados

---

### 6. Testes de multi-tenant são obrigatórios para repositórios

Todo repositório que acessa dados de tenant deve ter ao menos um teste que verifica o isolamento:

```python
async def test_query_does_not_return_data_from_other_tenant(self, session):
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())

    await UserFactory.create(session, tenant_id=tenant_a)
    result = await self.repository.find_many(tenant_id=tenant_b)

    assert result == []
```

---

## Resumo

| Camada      | O que testa                          | Usa banco? | Usa HTTP? | Usa Factory?  |
|-------------|--------------------------------------|------------|-----------|---------------|
| Unit        | Entidades, Use Cases, Domain Services | ❌         | ❌        | `.make()`     |
| Integration | Repositórios SQLAlchemy              | ✅         | ❌        | `.create()`   |
| E2E         | Rotas HTTP completas                 | ✅         | ✅        | `.create()`   |
