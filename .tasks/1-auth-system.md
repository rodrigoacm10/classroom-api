# Task 1 — Sistema de Autenticação (Sprint 4)

> **Objetivo**: Implementar o ciclo completo de autenticação com suporte a
> multi-tenancy. O `User` é uma identidade global do sistema; a **role** é
> definida pela relação entre o usuário e uma tenant específica.  
> **Entrega esperada**: `POST /users`, `POST /auth/login`,
> `POST /auth/switch-tenant`, rotas protegidas por `Depends(require_role(...))`.

---

## Conceito central — por que role não fica no User?

O `User` representa **quem a pessoa é** no sistema (identidade global).
A **role** representa **o que ela pode fazer dentro de uma tenant específica**.

```
users                          tenant_members
─────────────────              ─────────────────────────────────────────
id                             id
name                           user_id  ──────────────────→ users.id
email                          tenant_id ─────────────────→ tenants.id
password_hash                  role (admin | professor | aluno | coordenador)
fcm_token
created_at
```

> Um mesmo usuário pode ser **professor** na Tenant A e **coordenador** na
> Tenant B. Isso é impossível se a role ficar no `User`.

### Fluxo de autenticação em duas etapas

```
1. POST /auth/login
   email + password → JWT base (só contém user_id, sem tenant)

2. POST /auth/switch-tenant
   tenant_id + JWT base → JWT enriquecido (contém user_id + tenant_id + role)

   Todas as requisições subsequentes usam o JWT enriquecido.
   O backend sabe quem é o usuário E em qual tenant E qual o seu papel.
```

### Estrutura do JWT

```json
// Token base (logo após o login)
{ "sub": "uuid-do-user", "tenant_id": null, "role": null, "exp": ... }

// Token enriquecido (após selecionar a tenant)
{ "sub": "uuid-do-user", "tenant_id": "uuid-da-tenant", "role": "professor", "exp": ... }
```

---

## Visão geral da ordem de implementação

```
shared/enums/user_role.py           ← 1. Enum de roles (agora de membership)
        │
modules/user/
  domain/entities/user.py           ← 2. Entidade User (SEM role)
  domain/repositories/              ← 3. Interface (Protocol)
  infra/database/models/user.py     ← 4. Model SQLAlchemy (SEM role)
  infra/mappers/user_mapper.py      ← 5. Conversão Model ↔ Entity
  infra/repositories/               ← 6. Implementação SQLAlchemy
  application/use_cases/            ← 7. Casos de uso
  interface/schemas/                ← 8. Schemas Pydantic
  interface/router.py               ← 9. Rotas HTTP
        │
alembic/versions/001_create_users   ← 10. Migration (só tabela users)
        │
security/
  password.py                       ← 11. Hash de senha
  jwt.py                            ← 12. Gerar/verificar token (com tenant_id + role opcionais)
  dependencies/current_user.py      ← 13. get_current_user + AuthContext
  dependencies/require_role.py      ← 14. Autorização por role (lida do JWT)
        │
modules/auth/
  application/use_cases/login.py        ← 15. Gera JWT base
  application/use_cases/switch_tenant.py← 16. Troca JWT base por JWT enriquecido
  interface/router.py               ← 17. POST /auth/login + POST /auth/switch-tenant
        │
main.py                             ← 18. Registrar routers
```

> **Nota**: O módulo `tenant/` e o model `TenantMember` serão criados na
> **Task 2**. Nesta task, o `switch-tenant` é preparado mas depende
> da existência da tabela `tenant_members` — isso está marcado no checklist.

---

## Passo 1 — `shared/enums/user_role.py`

O enum continua existindo, mas agora representa a **role dentro de uma tenant**,
não um atributo permanente do usuário.

```python
# src/shared/enums/user_role.py
import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PROFESSOR = "professor"
    ALUNO = "aluno"
    COORDENADOR = "coordenador"
```

Criar também `src/shared/__init__.py` e `src/shared/enums/__init__.py` vazios.

---

## Passo 2 — Entidade de Domínio `User` (sem role)

```python
# src/modules/user/domain/entities/user.py
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class User:
    name: str
    email: str
    password_hash: str
    id: UUID = field(default_factory=uuid4)
    fcm_token: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
```

> Sem `role`. A identidade do usuário é independente de qualquer tenant.

---

## Passo 3 — Interface do Repositório (Protocol)

```python
# src/modules/user/domain/repositories/user_repository.py
from typing import Protocol
from uuid import UUID

from modules.user.domain.entities.user import User


class UserRepository(Protocol):

    async def find_by_id(self, user_id: UUID) -> User | None: ...

    async def find_by_email(self, email: str) -> User | None: ...

    async def save(self, user: User) -> User: ...
```

---

## Passo 4 — Model SQLAlchemy `UserModel` (sem role)

```python
# src/infra/database/models/user.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infra.database.base import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    fcm_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

> **Sem coluna `role`**. O enum `UserRole` não pertence à tabela `users`.

Registrar em `src/infra/database/models/__init__.py`:

```python
from infra.database.models.user import UserModel  # noqa: F401
```

---

## Passo 5 — Mapper `user_mapper.py`

```python
# src/modules/user/infra/mappers/user_mapper.py
from infra.database.models.user import UserModel
from modules.user.domain.entities.user import User


class UserMapper:

    @staticmethod
    def to_domain(model: UserModel) -> User:
        return User(
            id=model.id,
            name=model.name,
            email=model.email,
            password_hash=model.password_hash,
            fcm_token=model.fcm_token,
            created_at=model.created_at,
        )

    @staticmethod
    def to_model(entity: User) -> UserModel:
        return UserModel(
            id=entity.id,
            name=entity.name,
            email=entity.email,
            password_hash=entity.password_hash,
            fcm_token=entity.fcm_token,
        )
```

---

## Passo 6 — Repositório SQLAlchemy

```python
# src/modules/user/infra/repositories/user_sqlalchemy_repository.py
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.user import UserModel
from modules.user.domain.entities.user import User
from modules.user.infra.mappers.user_mapper import UserMapper


class UserSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_id(self, user_id: UUID) -> User | None:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return UserMapper.to_domain(model) if model else None

    async def find_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return UserMapper.to_domain(model) if model else None

    async def save(self, user: User) -> User:
        model = UserMapper.to_model(user)
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return UserMapper.to_domain(model)
```

---

## Passo 7 — Casos de Uso

### `create_user.py`

```python
# src/modules/user/application/use_cases/create_user.py
from dataclasses import dataclass

from modules.user.domain.entities.user import User
from modules.user.domain.repositories.user_repository import UserRepository
from security.password import hash_password


@dataclass
class CreateUserInput:
    name: str
    email: str
    password: str


class CreateUserUseCase:

    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def execute(self, data: CreateUserInput) -> User:
        existing = await self.repository.find_by_email(data.email)
        if existing:
            raise ValueError("E-mail já cadastrado.")

        user = User(
            name=data.name,
            email=data.email,
            password_hash=hash_password(data.password),
        )

        return await self.repository.save(user)
```

### `get_user.py`

```python
# src/modules/user/application/use_cases/get_user.py
from uuid import UUID

from modules.user.domain.entities.user import User
from modules.user.domain.repositories.user_repository import UserRepository


class GetUserUseCase:

    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def execute(self, user_id: UUID) -> User:
        user = await self.repository.find_by_id(user_id)
        if not user:
            raise ValueError("Usuário não encontrado.")
        return user
```

---

## Passo 8 — Schemas Pydantic

```python
# src/modules/user/interface/schemas/user_schemas.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

---

## Passo 9 — Router HTTP (`user`)

```python
# src/modules/user/interface/router.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.user.application.use_cases.create_user import CreateUserInput, CreateUserUseCase
from modules.user.infra.repositories.user_sqlalchemy_repository import UserSQLAlchemyRepository
from modules.user.interface.schemas.user_schemas import CreateUserRequest, UserResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    repository = UserSQLAlchemyRepository(session=db)
    use_case = CreateUserUseCase(repository=repository)

    try:
        user = await use_case.execute(
            CreateUserInput(name=body.name, email=body.email, password=body.password)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        created_at=user.created_at,
    )
```

---

## Passo 10 — Migration Alembic

```bash
uv run alembic revision --autogenerate -m "create users table"
uv run alembic upgrade head
```

Revisar o arquivo gerado — confirmar que **não há coluna `role`** na tabela `users`.

---

## Passo 11 — `security/password.py`

```python
# src/security/password.py
from pwdlib import PasswordHash

pwd_context = PasswordHash.recommended()


def hash_password(plain_password: str) -> str:
    """Retorna o hash seguro da senha."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Retorna True se a senha bate com o hash."""
    return pwd_context.verify(plain_password, hashed_password)
```

---

## Passo 12 — `security/jwt.py`

O JWT agora suporta contexto de tenant opcionalmente.

```python
# src/security/jwt.py
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from config.settings import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 horas


def create_access_token(
    user_id: UUID,
    tenant_id: UUID | None = None,
    role: str | None = None,
) -> str:
    """
    Gera um token JWT.

    - Sem tenant_id/role: token base (logo após o login).
    - Com tenant_id/role: token enriquecido (após switch-tenant).
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decodifica e valida o token JWT.
    Lança jwt.ExpiredSignatureError ou jwt.InvalidTokenError em caso de falha.
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
```

---

## Passo 13 — `security/dependencies/current_user.py`

Além do `User`, expõe o contexto da tenant ativa (`tenant_id` e `role`)
extraídos diretamente do JWT — sem ir ao banco para buscar a role.

```python
# src/security/dependencies/current_user.py
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.user.domain.entities.user import User
from modules.user.infra.repositories.user_sqlalchemy_repository import UserSQLAlchemyRepository
from security.jwt import decode_access_token
from shared.enums.user_role import UserRole

bearer_scheme = HTTPBearer()


@dataclass
class AuthContext:
    """Contexto completo de uma requisição autenticada."""
    user: User
    tenant_id: UUID | None        # None se o usuário não selecionou uma tenant ainda
    role: UserRole | None         # None se ainda não está em contexto de tenant


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")

    user_id = UUID(payload["sub"])
    repository = UserSQLAlchemyRepository(session=db)
    user = await repository.find_by_id(user_id)

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado.")

    raw_tenant_id = payload.get("tenant_id")
    raw_role = payload.get("role")

    return AuthContext(
        user=user,
        tenant_id=UUID(raw_tenant_id) if raw_tenant_id else None,
        role=UserRole(raw_role) if raw_role else None,
    )


# Atalho conveniente para rotas que só precisam do User (sem contexto de tenant)
async def get_current_user(
    ctx: AuthContext = Depends(get_auth_context),
) -> User:
    return ctx.user
```

---

## Passo 14 — `security/dependencies/require_role.py`

Bloqueia acesso se o usuário não estiver em uma tenant ativa com a role exigida.

```python
# src/security/dependencies/require_role.py
from fastapi import Depends, HTTPException, status

from security.dependencies.current_user import AuthContext, get_auth_context
from shared.enums.user_role import UserRole


def require_role(*roles: UserRole):
    """
    Exige que o token tenha contexto de tenant E que a role seja uma das permitidas.

    Uso no router:
        @router.post("/sessions", dependencies=[Depends(require_role(UserRole.PROFESSOR))])
    """
    async def dependency(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if ctx.tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nenhuma tenant selecionada. Use POST /auth/switch-tenant.",
            )
        if ctx.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso não autorizado para este perfil.",
            )
        return ctx

    return dependency
```

---

## Passo 15 — Caso de Uso `login.py`

Gera um **token base** — sem tenant_id, sem role.

```python
# src/modules/auth/application/use_cases/login.py
from dataclasses import dataclass

from modules.user.domain.repositories.user_repository import UserRepository
from security.jwt import create_access_token
from security.password import verify_password


@dataclass
class LoginInput:
    email: str
    password: str


@dataclass
class LoginOutput:
    access_token: str
    token_type: str = "bearer"


class LoginUseCase:

    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def execute(self, data: LoginInput) -> LoginOutput:
        user = await self.repository.find_by_email(data.email)

        if not user or not verify_password(data.password, user.password_hash):
            raise ValueError("Credenciais inválidas.")

        # Token base: identifica o usuário, mas sem contexto de tenant
        token = create_access_token(user_id=user.id)
        return LoginOutput(access_token=token)
```

---

## Passo 16 — Caso de Uso `switch_tenant.py`

Troca o token base por um **token enriquecido** com tenant_id + role.

> ⚠️ Este caso de uso **depende do módulo `tenant/`** (Task 2), que ainda não
> existe. Implemente o esqueleto agora e complete quando a Task 2 estiver pronta.

```python
# src/modules/auth/application/use_cases/switch_tenant.py
from dataclasses import dataclass
from uuid import UUID

from modules.user.domain.entities.user import User
from security.jwt import create_access_token


@dataclass
class SwitchTenantInput:
    user: User
    tenant_id: UUID


@dataclass
class SwitchTenantOutput:
    access_token: str
    token_type: str = "bearer"


class SwitchTenantUseCase:
    """
    Verifica se o usuário é membro da tenant informada e,
    se for, retorna um JWT enriquecido com tenant_id + role.

    Depende de TenantMemberRepository (Task 2).
    Deixe como NotImplementedError até a Task 2 ser concluída.
    """

    async def execute(self, data: SwitchTenantInput) -> SwitchTenantOutput:
        # TODO (Task 2): buscar TenantMember(user_id=data.user.id, tenant_id=data.tenant_id)
        # Se não encontrar → raise ValueError("Usuário não é membro desta tenant.")
        # role = member.role

        raise NotImplementedError("Aguardando Task 2 — módulo tenant/")
```

---

## Passo 17 — Router `auth`

```python
# src/modules/auth/interface/router.py
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.auth.application.use_cases.login import LoginInput, LoginUseCase
from modules.auth.application.use_cases.switch_tenant import SwitchTenantInput, SwitchTenantUseCase
from modules.user.infra.repositories.user_sqlalchemy_repository import UserSQLAlchemyRepository
from security.dependencies.current_user import get_current_user
from modules.user.domain.entities.user import User

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SwitchTenantRequest(BaseModel):
    tenant_id: UUID


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    repository = UserSQLAlchemyRepository(session=db)
    use_case = LoginUseCase(repository=repository)

    try:
        result = await use_case.execute(LoginInput(email=body.email, password=body.password))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    return TokenResponse(access_token=result.access_token, token_type=result.token_type)


@router.post("/switch-tenant", response_model=TokenResponse)
async def switch_tenant(
    body: SwitchTenantRequest,
    current_user: User = Depends(get_current_user),
) -> TokenResponse:
    """
    Recebe o JWT base (sem tenant) e devolve um JWT enriquecido com tenant_id + role.
    Requer que o usuário seja membro da tenant informada.
    """
    use_case = SwitchTenantUseCase()

    try:
        result = await use_case.execute(
            SwitchTenantInput(user=current_user, tenant_id=body.tenant_id)
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return TokenResponse(access_token=result.access_token, token_type=result.token_type)
```

---

## Passo 18 — Registrar os Routers no `main.py`

```python
# src/main.py
from fastapi import FastAPI

from config.settings import settings
from modules.auth.interface.router import router as auth_router
from modules.user.interface.router import router as user_router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.include_router(auth_router)
app.include_router(user_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "API is running"}
```

---

## Estrutura de arquivos resultante

```
src/
├── shared/
│   └── enums/
│       └── user_role.py          ← role de membership (não do user)
│
├── config/
│   └── settings.py               (já existe)
│
├── infra/
│   └── database/
│       ├── base.py               (já existe)
│       ├── session.py            (já existe)
│       └── models/
│           ├── __init__.py       (registrar UserModel)
│           └── user.py           ← SEM coluna role
│
├── security/
│   ├── password.py
│   ├── jwt.py                    ← suporta tenant_id + role opcionais
│   └── dependencies/
│       ├── current_user.py       ← retorna AuthContext (user + tenant_id + role)
│       └── require_role.py       ← lê role do JWT, exige tenant ativa
│
└── modules/
    ├── user/
    │   ├── domain/
    │   │   ├── entities/user.py              ← SEM campo role
    │   │   └── repositories/user_repository.py
    │   ├── application/use_cases/
    │   │   ├── create_user.py                ← SEM role no input
    │   │   └── get_user.py
    │   ├── infra/
    │   │   ├── mappers/user_mapper.py
    │   │   └── repositories/user_sqlalchemy_repository.py
    │   └── interface/
    │       ├── router.py
    │       └── schemas/user_schemas.py       ← SEM role na resposta
    │
    └── auth/
        ├── application/use_cases/
        │   ├── login.py                      ← retorna JWT base
        │   └── switch_tenant.py              ← retorna JWT enriquecido (TODO Task 2)
        └── interface/router.py               ← /auth/login + /auth/switch-tenant

alembic/versions/
    └── 001_xxxx_create_users_table.py        ← SEM coluna role
```

---

## O que muda na Task 2 (Tenant)

Quando a Task 2 for implementada, o `SwitchTenantUseCase` será completado:

```python
# Task 2 irá criar:
# - TenantModel (tabela tenants)
# - TenantMemberModel (tabela tenant_members: user_id + tenant_id + role)
# - TenantMemberRepository
#
# E completar switch_tenant.py:
#   member = await tenant_member_repo.find(user_id, tenant_id)
#   if not member: raise ValueError(...)
#   token = create_access_token(user_id, tenant_id, member.role)
```

---

## Checklist de entrega

- [ ] `shared/enums/user_role.py` criado (sem atrelar ao User)
- [ ] Entidade `User` criada **sem campo `role`**
- [ ] `UserRepository` Protocol definido
- [ ] `UserModel` criado **sem coluna `role`** e registrado em `models/__init__.py`
- [ ] `UserMapper` criado
- [ ] `UserSQLAlchemyRepository` criado
- [ ] Casos de uso `CreateUser` e `GetUser` criados
- [ ] Schemas Pydantic criados (sem `role`)
- [ ] Router `user` registrado (`POST /users`)
- [ ] Migration gerada e aplicada — confirmar ausência de coluna `role` em `users`
- [ ] `security/password.py` criado
- [ ] `security/jwt.py` criado com suporte a `tenant_id` e `role` opcionais
- [ ] `security/dependencies/current_user.py` criado com `AuthContext`
- [ ] `security/dependencies/require_role.py` criado (lê role do JWT)
- [ ] Caso de uso `LoginUseCase` criado (JWT base)
- [ ] Caso de uso `SwitchTenantUseCase` criado (esqueleto com `NotImplementedError`)
- [ ] Router `auth` registrado (`POST /auth/login` + `POST /auth/switch-tenant`)
- [ ] `main.py` atualizado com os dois routers
- [ ] `POST /users` testado no Swagger
- [ ] `POST /auth/login` testado — confirmar que o token **não contém role**
- [ ] `POST /auth/switch-tenant` retorna `501 Not Implemented` (aguardando Task 2)

---

## Testando no Swagger

Com o servidor rodando (`uv run uvicorn src.main:app --reload`):

1. `POST /users` — cadastre um usuário (sem informar role)
2. `POST /auth/login` — faça login; decodifique o token em [jwt.io](https://jwt.io)
   e confirme: `"tenant_id": null, "role": null`
3. Copie o token e clique em **Authorize** no Swagger
4. `POST /auth/switch-tenant` com qualquer `tenant_id` — deve retornar `501`
   (será completado na Task 2)
5. Tente acessar uma rota protegida com `require_role(UserRole.PROFESSOR)` usando
   o token base — deve retornar `403 Nenhuma tenant selecionada`
