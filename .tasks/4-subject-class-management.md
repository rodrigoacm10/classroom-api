# Task 4 — Módulo de Turmas por Disciplina (`SubjectClass`) com Vinculação a Salas

> **Objetivo**: Implementar o cadastro e gerenciamento de Turmas de Disciplinas (`SubjectClass`) de uma
> Tenant/Instituição. Cada turma é criada por um professor, pode ter alunos matriculados
> (relação N:N via `subject_class_students`) e é **vinculada a uma Sala (`Room`)** para fins de
> validação geoespacial nas sessões de chamada.
>
> **Entrega esperada**: `POST /tenants/{tenant_id}/subject-classes`,
> `GET /tenants/{tenant_id}/subject-classes`, `GET /tenants/{tenant_id}/subject-classes/{subject_class_id}`,
> `PATCH /tenants/{tenant_id}/subject-classes/{subject_class_id}`,
> `DELETE /tenants/{tenant_id}/subject-classes/{subject_class_id}`.

---

## Conceito central — Vinculação `SubjectClass ↔ Room`

Uma turma de disciplina referencia uma sala física como seu **local padrão**. Essa vinculação é a ponte
entre o módulo de turmas e o sistema de validação geoespacial: quando uma `AttendanceSession`
é aberta, ela herda o ponto GPS e o raio de tolerância da sala vinculada à turma.

```
SubjectClass (turma de disciplina)
  ├── professor_id  → FK users.id
  ├── room_id       → FK rooms.id  (local físico padrão)
  └── tenant_id     → FK tenants.id

AttendanceSession (chamada)
  ├── subject_class_id → FK subject_classes.id
  └── room_id          → FK rooms.id  (pode ser sobrescrito no momento da chamada)
```

> **Regra de negócio**: `room_id` é **obrigatório** na criação da turma.
> A sala vinculada **não pode estar com `deleted = True`** — tentar criar ou
> atualizar uma turma apontando para uma sala deletada deve retornar `404 Not Found`
> com a mensagem `"Sala não encontrada."`.

---

## Padrão Soft Delete (igual ao módulo Room)

A `SubjectClass` segue o mesmo padrão de deleção lógica já estabelecido no módulo `Room`:

| Operação | Comportamento |
|---|---|
| `DELETE /subject-classes/{id}` | Seta `deleted = True` no banco — **nunca** remove a linha |
| `GET /subject-classes` (listagem) | **Jamais** retorna registros com `deleted = True` |
| `GET /subject-classes/{id}` | Retorna `404` se `deleted = True` |
| `PATCH /subject-classes/{id}` | Retorna `404` se `deleted = True` |
| `DELETE /subject-classes/{id}` (repetido) | Retorna `404` se `deleted = True` |

> **Atenção**: A flag `deleted` é um detalhe de infraestrutura — ela **nunca deve
> aparecer no response JSON** da API. O `SubjectClassResponse` não deve expor esse campo.

---

## Controle de Erros (exceções esperadas)

Todos os erros de negócio devem lançar exceções do módulo `shared.exceptions`,
que o middleware global da aplicação converte automaticamente em respostas HTTP.

| Situação | Exceção | Código HTTP |
|---|---|---|
| Turma não encontrada (inexistente ou `deleted=True`) | `ResourceNotFoundException` | `404` |
| Tenant não encontrada ou deletada | `ResourceNotFoundException` | `404` |
| Sala (`room_id`) não encontrada ou deletada | `ResourceNotFoundException` | `404` |
| Sala pertence a uma tenant diferente | `ResourceNotFoundException` | `404` |
| Usuário sem permissão (`ALUNO` tentando criar/editar/deletar) | `ForbiddenException` (via `require_role`) | `403` |
| Validação de schema Pydantic (ex: `name` vazio) | Pydantic `ValidationError` | `422` |

---

## Visão geral da ordem de implementação

```
infra/database/models/subject_class.py               ← 1. Model SQLAlchemy SubjectClassModel
alembic/versions/XXX_create_subject_classes_table.py ← 2. Migration
modules/subject_class/
  domain/entities/subject_class.py                   ← 3. Entidade de domínio SubjectClass
  domain/repositories/subject_class_repository.py     ← 4. Protocol (interface) do repositório
  infra/mappers/subject_class_mapper.py               ← 5. Mapper Model ↔ Entity
  infra/repositories/subject_class_sqlalchemy_repository.py ← 6. Implementação SQLAlchemy
  application/use_cases/create_subject_class.py      ← 7. CreateSubjectClassUseCase
  application/use_cases/get_subject_class.py         ← 8. GetSubjectClassUseCase
  application/use_cases/list_subject_classes.py      ← 9. ListSubjectClassesUseCase
  application/use_cases/update_subject_class.py      ← 10. UpdateSubjectClassUseCase
  application/use_cases/delete_subject_class.py      ← 11. DeleteSubjectClassUseCase
  interface/schemas/subject_class_schemas.py        ← 12. Schemas Pydantic (request/response)
  interface/router.py                                ← 13. Router HTTP com 5 rotas
main.py                                              ← 14. Registrar o router na aplicação
tests/                                               ← 15. Testes unitários, integração e E2E
```

---

## Passo 1 — Model SQLAlchemy `SubjectClassModel`

```python
# src/infra/database/models/subject_class.py
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, false, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infra.database.base import Base


class SubjectClassModel(Base):
    __tablename__ = "subject_classes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    professor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_members.id", ondelete="SET NULL"), nullable=True
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    discipline_name: Mapped[str] = mapped_column(String(255), nullable=False)
    deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

> **Notas de design:**
> - `room_id` usa `ondelete="SET NULL"` — se a sala for removida do banco (hard delete
>   eventual ou limpeza manual), a turma não é perdida, apenas fica sem sala vinculada.
> - `professor_id` usa `ondelete="SET NULL"` pelo mesmo motivo.
> - `ondelete="CASCADE"` no `tenant_id` garante que ao deletar a tenant, todas as suas
>   turmas são removidas automaticamente.
> - `discipline_name` é obrigatório — representa o nome da disciplina ensinada na turma.
> - A coluna `deleted` segue exatamente o mesmo padrão do `RoomModel`.

---

## Passo 2 — Migration Alembic

```bash
uv run alembic revision --autogenerate -m "create subject_classes table"
uv run alembic upgrade head
```

A migration criará (aproximadamente):

```sql
CREATE TABLE subject_classes (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    professor_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    room_id          UUID REFERENCES rooms(id) ON DELETE SET NULL,
    name             VARCHAR(255) NOT NULL,
    discipline_name  VARCHAR(255) NOT NULL,
    deleted          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now()
);

-- Índice para acelerar listagens por tenant
CREATE INDEX idx_subject_classes_tenant_id ON subject_classes(tenant_id);

-- Índice para acelerar buscas por professor
CREATE INDEX idx_subject_classes_professor_id ON subject_classes(professor_id);
```

---

## Passo 3 — Entidade de Domínio `SubjectClass`

```python
# src/modules/subject_class/domain/entities/subject_class.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass
class SubjectClass:
    tenant_id: UUID
    professor_id: UUID
    room_id: UUID
    name: str
    discipline_name: str
    deleted: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

> **Notas de design:**
> - A entidade de domínio **não conhece** SQLAlchemy, FastAPI nem Pydantic.
> - `room_id` é armazenado como `UUID` puro — o domínio não navega pela relação ORM.
> - `professor_id` é quem criou/gerencia a turma.
> - `deleted` segue o mesmo padrão da entidade `Room`.

---

## Passo 4 — Interface do Repositório (Protocol)

```python
# src/modules/subject_class/domain/repositories/subject_class_repository.py
from typing import Protocol
from uuid import UUID

from modules.subject_class.domain.entities.subject_class import SubjectClass


class SubjectClassRepository(Protocol):

    async def save(self, subject_class: SubjectClass) -> SubjectClass: ...

    async def find_by_id(
        self, subject_class_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None: ...

    async def find_by_id_and_tenant(
        self, subject_class_id: UUID, tenant_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None: ...

    async def list_by_tenant(
        self, tenant_id: UUID, include_deleted: bool = False
    ) -> list[SubjectClass]: ...

    async def delete(self, subject_class: SubjectClass) -> None: ...
```

> **Atenção**: O parâmetro `include_deleted` deve ser respeitado rigorosamente em todas
> as implementações (repositório real e fake). Por padrão é `False`, ou seja, registros
> com `deleted = True` são **invisíveis** a menos que explicitamente solicitados.

---

## Passo 5 — Mapper `SubjectClassMapper`

```python
# src/modules/subject_class/infra/mappers/subject_class_mapper.py
from infra.database.models.subject_class import SubjectClassModel
from modules.subject_class.domain.entities.subject_class import SubjectClass


class SubjectClassMapper:

    @staticmethod
    def to_domain(model: SubjectClassModel) -> SubjectClass:
        return SubjectClass(
            id=model.id,
            tenant_id=model.tenant_id,
            professor_id=model.professor_id,
            room_id=model.room_id,
            name=model.name,
            discipline_name=model.discipline_name,
            deleted=model.deleted,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: SubjectClass) -> SubjectClassModel:
        return SubjectClassModel(
            id=entity.id,
            tenant_id=entity.tenant_id,
            professor_id=entity.professor_id,
            room_id=entity.room_id,
            name=entity.name,
            discipline_name=entity.discipline_name,
            deleted=entity.deleted,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
```

---

## Passo 6 — Repositório SQLAlchemy `SubjectClassSQLAlchemyRepository`

```python
# src/modules/subject_class/infra/repositories/subject_class_sqlalchemy_repository.py
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.subject_class import SubjectClassModel
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.infra.mappers.subject_class_mapper import SubjectClassMapper


class SubjectClassSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, subject_class: SubjectClass) -> SubjectClass:
        model = SubjectClassMapper.to_model(subject_class)
        merged = await self.session.merge(model)
        await self.session.commit()
        await self.session.refresh(merged)
        return SubjectClassMapper.to_domain(merged)

    async def find_by_id(
        self, subject_class_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None:
        stmt = select(SubjectClassModel).where(SubjectClassModel.id == subject_class_id)
        if not include_deleted:
            stmt = stmt.where(SubjectClassModel.deleted == False)  # noqa: E712
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return SubjectClassMapper.to_domain(model) if model else None

    async def find_by_id_and_tenant(
        self, subject_class_id: UUID, tenant_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None:
        stmt = select(SubjectClassModel).where(
            SubjectClassModel.id == subject_class_id,
            SubjectClassModel.tenant_id == tenant_id,
        )
        if not include_deleted:
            stmt = stmt.where(SubjectClassModel.deleted == False)  # noqa: E712
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return SubjectClassMapper.to_domain(model) if model else None

    async def list_by_tenant(
        self, tenant_id: UUID, include_deleted: bool = False
    ) -> list[SubjectClass]:
        stmt = select(SubjectClassModel).where(SubjectClassModel.tenant_id == tenant_id)
        if not include_deleted:
            stmt = stmt.where(SubjectClassModel.deleted == False)  # noqa: E712
        result = await self.session.execute(stmt)
        return [SubjectClassMapper.to_domain(m) for m in result.scalars().all()]

    async def delete(self, subject_class: SubjectClass) -> None:
        subject_class.deleted = True
        await self.save(subject_class)
```

---

## Passo 7 — Casos de Uso

### 7.1 `CreateSubjectClassUseCase`

```python
# src/modules/subject_class/application/use_cases/create_subject_class.py
from dataclasses import dataclass
from uuid import UUID

from modules.room.domain.repositories.room_repository import RoomRepository
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class CreateSubjectClassInput:
    tenant_id: UUID
    professor_id: UUID
    room_id: UUID
    name: str
    discipline_name: str


class CreateSubjectClassUseCase:

    def __init__(
        self,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
        room_repo: RoomRepository,
    ) -> None:
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo
        self.room_repo = room_repo

    async def execute(self, data: CreateSubjectClassInput) -> SubjectClass:
        # 1. Verifica tenant
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        # 2. Verifica sala — inclui checar se pertence à mesma tenant e se não foi deletada
        room = await self.room_repo.find_by_id_and_tenant(
            room_id=data.room_id,
            tenant_id=data.tenant_id,
        )
        if not room:
            raise ResourceNotFoundException("Sala não encontrada.")

        # 3. Cria e persiste a entidade
        subject_class = SubjectClass(
            tenant_id=data.tenant_id,
            professor_id=data.professor_id,
            room_id=data.room_id,
            name=data.name,
            discipline_name=data.discipline_name,
        )
        return await self.subject_class_repo.save(subject_class)
```

> **Atenção**: `find_by_id_and_tenant` já filtra `deleted = False` por padrão — logo,
> uma sala soft-deletada será invisível e o use case lançará `ResourceNotFoundException`.

### 7.2 `GetSubjectClassUseCase`

```python
# src/modules/subject_class/application/use_cases/get_subject_class.py
from dataclasses import dataclass
from uuid import UUID

from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class GetSubjectClassInput:
    subject_class_id: UUID
    tenant_id: UUID


class GetSubjectClassUseCase:

    def __init__(self, subject_class_repo: SubjectClassRepository) -> None:
        self.subject_class_repo = subject_class_repo

    async def execute(self, data: GetSubjectClassInput) -> SubjectClass:
        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            subject_class_id=data.subject_class_id,
            tenant_id=data.tenant_id,
        )
        if not subject_class:
            raise ResourceNotFoundException("Turma não encontrada.")
        return subject_class
```

### 7.3 `ListSubjectClassesUseCase`

```python
# src/modules/subject_class/application/use_cases/list_subject_classes.py
from dataclasses import dataclass
from uuid import UUID

from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class ListSubjectClassesInput:
    tenant_id: UUID


class ListSubjectClassesUseCase:

    def __init__(
        self,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: ListSubjectClassesInput) -> list[SubjectClass]:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        # include_deleted=False (padrão) — turmas deletadas NÃO aparecem na listagem
        return await self.subject_class_repo.list_by_tenant(data.tenant_id)
```

### 7.4 `UpdateSubjectClassUseCase`

```python
# src/modules/subject_class/application/use_cases/update_subject_class.py
from dataclasses import dataclass
from uuid import UUID

from modules.room.domain.repositories.room_repository import RoomRepository
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class UpdateSubjectClassInput:
    subject_class_id: UUID
    tenant_id: UUID
    name: str | None = None
    discipline_name: str | None = None
    room_id: UUID | None = None


class UpdateSubjectClassUseCase:

    def __init__(
        self,
        subject_class_repo: SubjectClassRepository,
        room_repo: RoomRepository,
    ) -> None:
        self.subject_class_repo = subject_class_repo
        self.room_repo = room_repo

    async def execute(self, data: UpdateSubjectClassInput) -> SubjectClass:
        # 1. Busca a turma (retorna None se não existe ou se deleted=True)
        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            subject_class_id=data.subject_class_id,
            tenant_id=data.tenant_id,
        )
        if not subject_class:
            raise ResourceNotFoundException("Turma não encontrada.")

        # 2. Se room_id foi enviado, valida a nova sala
        if data.room_id is not None:
            room = await self.room_repo.find_by_id_and_tenant(
                room_id=data.room_id,
                tenant_id=data.tenant_id,
            )
            if not room:
                raise ResourceNotFoundException("Sala não encontrada.")
            subject_class.room_id = data.room_id

        if data.name is not None:
            subject_class.name = data.name
        if data.discipline_name is not None:
            subject_class.discipline_name = data.discipline_name

        return await self.subject_class_repo.save(subject_class)
```

### 7.5 `DeleteSubjectClassUseCase`

```python
# src/modules/subject_class/application/use_cases/delete_subject_class.py
from dataclasses import dataclass
from uuid import UUID

from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class DeleteSubjectClassInput:
    subject_class_id: UUID
    tenant_id: UUID


class DeleteSubjectClassUseCase:

    def __init__(self, subject_class_repo: SubjectClassRepository) -> None:
        self.subject_class_repo = subject_class_repo

    async def execute(self, data: DeleteSubjectClassInput) -> None:
        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            subject_class_id=data.subject_class_id,
            tenant_id=data.tenant_id,
        )
        if not subject_class:
            raise ResourceNotFoundException("Turma não encontrada.")

        await self.subject_class_repo.delete(subject_class)
```

---

## Passo 8 — Schemas Pydantic

```python
# src/modules/subject_class/interface/schemas/subject_class_schemas.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateSubjectClassRequest(BaseModel):
    room_id: UUID = Field(..., description="ID da sala física onde a turma ocorre.")
    name: str = Field(..., min_length=1, max_length=255, examples=["Turma A — Noturno"])
    discipline_name: str = Field(..., min_length=1, max_length=255, examples=["Banco de Dados"])


class UpdateSubjectClassRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    discipline_name: str | None = Field(default=None, min_length=1, max_length=255)
    room_id: UUID | None = Field(default=None, description="Alterar a sala vinculada à turma.")


class SubjectClassResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    professor_id: UUID
    room_id: UUID
    name: str
    discipline_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

> **Atenção**: O campo `deleted` **não aparece** no `SubjectClassResponse`. A API nunca expõe
> essa flag — a invisibilidade de registros deletados é garantida na camada de repositório.

---

## Passo 9 — Router FastAPI

```python
# src/modules/subject_class/interface/router.py
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.room.infra.repositories.room_sqlalchemy_repository import RoomSQLAlchemyRepository
from modules.subject_class.application.use_cases.create_subject_class import (
    CreateSubjectClassInput,
    CreateSubjectClassUseCase,
)
from modules.subject_class.application.use_cases.delete_subject_class import (
    DeleteSubjectClassInput,
    DeleteSubjectClassUseCase,
)
from modules.subject_class.application.use_cases.get_subject_class import (
    GetSubjectClassInput,
    GetSubjectClassUseCase,
)
from modules.subject_class.application.use_cases.list_subject_classes import (
    ListSubjectClassesInput,
    ListSubjectClassesUseCase,
)
from modules.subject_class.application.use_cases.update_subject_class import (
    UpdateSubjectClassInput,
    UpdateSubjectClassUseCase,
)
from modules.subject_class.infra.repositories.subject_class_sqlalchemy_repository import (
    SubjectClassSQLAlchemyRepository,
)
from modules.subject_class.interface.schemas.subject_class_schemas import (
    CreateSubjectClassRequest,
    SubjectClassResponse,
    UpdateSubjectClassRequest,
)
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import TenantSQLAlchemyRepository
from modules.user.domain.entities.user import User
from security.dependencies.current_user import get_current_user
from security.dependencies.require_role import require_role
from shared.enums.user_role import UserRole

router = APIRouter(prefix="/tenants/{tenant_id}/subject-classes", tags=["subject-classes"])


@router.post(
    "",
    response_model=SubjectClassResponse,
    status_code=201,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def create_subject_class(
    tenant_id: UUID,
    body: CreateSubjectClassRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubjectClassResponse:
    """Cadastra uma nova turma de disciplina para a Tenant. Requer papel ADMIN ou PROFESSOR."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    room_repo = RoomSQLAlchemyRepository(session=db)
    use_case = CreateSubjectClassUseCase(
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        room_repo=room_repo,
    )
    subject_class = await use_case.execute(
        CreateSubjectClassInput(
            tenant_id=tenant_id,
            professor_id=current_user.id,
            room_id=body.room_id,
            name=body.name,
            discipline_name=body.discipline_name,
        )
    )
    return SubjectClassResponse.model_validate(subject_class)


@router.get("", response_model=list[SubjectClassResponse])
async def list_subject_classes(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[SubjectClassResponse]:
    """Lista todas as turmas ativas (não deletadas) de uma Tenant."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    use_case = ListSubjectClassesUseCase(subject_class_repo=subject_class_repo, tenant_repo=tenant_repo)

    classes = await use_case.execute(ListSubjectClassesInput(tenant_id=tenant_id))
    return [SubjectClassResponse.model_validate(c) for c in classes]


@router.get("/{subject_class_id}", response_model=SubjectClassResponse)
async def get_subject_class(
    tenant_id: UUID,
    subject_class_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SubjectClassResponse:
    """Retorna os detalhes de uma turma. Retorna 404 se deletada ou inexistente."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    use_case = GetSubjectClassUseCase(subject_class_repo=subject_class_repo)

    subject_class = await use_case.execute(
        GetSubjectClassInput(subject_class_id=subject_class_id, tenant_id=tenant_id)
    )
    return SubjectClassResponse.model_validate(subject_class)


@router.patch(
    "/{subject_class_id}",
    response_model=SubjectClassResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def update_subject_class(
    tenant_id: UUID,
    subject_class_id: UUID,
    body: UpdateSubjectClassRequest,
    db: AsyncSession = Depends(get_db),
) -> SubjectClassResponse:
    """Atualiza parcialmente os dados de uma turma. Retorna 404 se deletada."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    room_repo = RoomSQLAlchemyRepository(session=db)
    use_case = UpdateSubjectClassUseCase(subject_class_repo=subject_class_repo, room_repo=room_repo)

    subject_class = await use_case.execute(
        UpdateSubjectClassInput(
            subject_class_id=subject_class_id,
            tenant_id=tenant_id,
            name=body.name,
            discipline_name=body.discipline_name,
            room_id=body.room_id,
        )
    )
    return SubjectClassResponse.model_validate(subject_class)


@router.delete(
    "/{subject_class_id}",
    status_code=204,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def delete_subject_class(
    tenant_id: UUID,
    subject_class_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete de uma turma. Requer papel ADMIN. Retorna 404 se já deletada."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    use_case = DeleteSubjectClassUseCase(subject_class_repo=subject_class_repo)

    await use_case.execute(
        DeleteSubjectClassInput(subject_class_id=subject_class_id, tenant_id=tenant_id)
    )
```

---

## Passo 10 — Registrar o router em `main.py`

```python
# Adicionar junto aos outros routers em src/main.py
from modules.subject_class.interface.router import router as subject_class_router

app.include_router(subject_class_router)
```

---

## Passo 11 — Registrar `SubjectClassModel` em `infra/database/models/__init__.py`

```python
# src/infra/database/models/__init__.py
from infra.database.models.room import RoomModel
from infra.database.models.subject_class import SubjectClassModel
from infra.database.models.tenant import TenantMemberModel, TenantModel
from infra.database.models.tenant_invite import TenantInviteModel
from infra.database.models.user import UserModel

__all__ = [
    "UserModel",
    "TenantModel",
    "TenantMemberModel",
    "TenantInviteModel",
    "RoomModel",
    "SubjectClassModel",
]
```

---

## Passo 12 — Testes

### 12.1 Fake Repository (Testes Unitários)

```python
# tests/unit/fakes/fake_subject_class_repository.py
from uuid import UUID

from modules.subject_class.domain.entities.subject_class import SubjectClass


class FakeSubjectClassRepository:

    def __init__(self) -> None:
        self._classes: dict[UUID, SubjectClass] = {}

    async def save(self, subject_class: SubjectClass) -> SubjectClass:
        self._classes[subject_class.id] = subject_class
        return subject_class

    async def find_by_id(
        self, subject_class_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None:
        c = self._classes.get(subject_class_id)
        if c and (include_deleted or not c.deleted):
            return c
        return None

    async def find_by_id_and_tenant(
        self, subject_class_id: UUID, tenant_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None:
        c = self._classes.get(subject_class_id)
        if c and c.tenant_id == tenant_id and (include_deleted or not c.deleted):
            return c
        return None

    async def list_by_tenant(
        self, tenant_id: UUID, include_deleted: bool = False
    ) -> list[SubjectClass]:
        return [
            c for c in self._classes.values()
            if c.tenant_id == tenant_id and (include_deleted or not c.deleted)
        ]

    async def delete(self, subject_class: SubjectClass) -> None:
        subject_class.deleted = True
        await self.save(subject_class)
```

### 12.2 Cenários de Teste Esperados

#### Testes Unitários (`tests/unit/modules/subject_class/test_subject_class_use_cases.py`)

| Caso | Use Case | Resultado esperado |
|---|---|---|
| Criar turma com dados válidos | `CreateSubjectClassUseCase` | Retorna `SubjectClass` com todos os campos |
| Criar turma com tenant deletada | `CreateSubjectClassUseCase` | Lança `ResourceNotFoundException` |
| Criar turma com sala deletada | `CreateSubjectClassUseCase` | Lança `ResourceNotFoundException` |
| Criar turma com sala de outra tenant | `CreateSubjectClassUseCase` | Lança `ResourceNotFoundException` |
| Buscar turma existente | `GetSubjectClassUseCase` | Retorna a turma |
| Buscar turma deletada | `GetSubjectClassUseCase` | Lança `ResourceNotFoundException` |
| Listar turmas da tenant | `ListSubjectClassesUseCase` | Retorna apenas não-deletadas |
| Listar com tenant deletada | `ListSubjectClassesUseCase` | Lança `ResourceNotFoundException` |
| Atualizar nome e disciplina | `UpdateSubjectClassUseCase` | Campos atualizados, restante preservado |
| Atualizar room_id para sala válida | `UpdateSubjectClassUseCase` | `room_id` atualizado |
| Atualizar room_id para sala deletada | `UpdateSubjectClassUseCase` | Lança `ResourceNotFoundException` |
| Atualizar turma deletada | `UpdateSubjectClassUseCase` | Lança `ResourceNotFoundException` |
| Deletar turma existente | `DeleteSubjectClassUseCase` | `deleted=True`, sem retorno |
| Deletar turma já deletada | `DeleteSubjectClassUseCase` | Lança `ResourceNotFoundException` |

#### Testes de Integração (`tests/integration/modules/subject_class/test_subject_class_sqlalchemy_repository.py`)

| Caso | Verificação |
|---|---|
| `save` + `find_by_id` | Dados persistidos e recuperados corretamente |
| `list_by_tenant` exclui deletados | `deleted=True` não aparece na listagem padrão |
| `find_by_id_and_tenant` com tenant errada | Retorna `None` |
| `delete` seta `deleted=True` no banco | Registro persiste com flag setada |

#### Testes E2E (`tests/e2e/modules/subject_class/test_subject_class_router.py`)

| Caso | Rota | Status esperado |
|---|---|---|
| Criar turma (ADMIN) | `POST /tenants/{id}/subject-classes` | `201` |
| Criar turma (PROFESSOR) | `POST /tenants/{id}/subject-classes` | `201` |
| Criar turma (ALUNO) | `POST /tenants/{id}/subject-classes` | `403` |
| Criar turma com sala deletada | `POST /tenants/{id}/subject-classes` | `404` |
| Criar turma com sala de outra tenant | `POST /tenants/{id}/subject-classes` | `404` |
| Criar turma com `name` vazio | `POST /tenants/{id}/subject-classes` | `422` |
| Listar turmas | `GET /tenants/{id}/subject-classes` | `200` (apenas ativas) |
| Buscar turma por ID | `GET /tenants/{id}/subject-classes/{id}` | `200` |
| Buscar turma deletada | `GET /tenants/{id}/subject-classes/{id}` | `404` |
| Atualizar turma (PROFESSOR) | `PATCH /tenants/{id}/subject-classes/{id}` | `200` |
| Atualizar turma (ALUNO) | `PATCH /tenants/{id}/subject-classes/{id}` | `403` |
| Atualizar turma deletada | `PATCH /tenants/{id}/subject-classes/{id}` | `404` |
| Atualizar `room_id` para sala deletada | `PATCH /tenants/{id}/subject-classes/{id}` | `404` |
| Deletar turma (ADMIN) | `DELETE /tenants/{id}/subject-classes/{id}` | `204` |
| Deletar turma (PROFESSOR) | `DELETE /tenants/{id}/subject-classes/{id}` | `403` |
| Deletar turma já deletada | `DELETE /tenants/{id}/subject-classes/{id}` | `404` |
| Listar após soft delete (turma não aparece) | `GET /tenants/{id}/subject-classes` | `200` (lista sem a turma) |

---

## Checklist de implementação

- [ ] Model SQLAlchemy `SubjectClassModel` criado em `src/infra/database/models/subject_class.py`
- [ ] `SubjectClassModel` registrado em `src/infra/database/models/__init__.py`
- [ ] Migration gerada e aplicada (`alembic revision --autogenerate`)
- [ ] Entidade de domínio `SubjectClass` criada em `src/modules/subject_class/domain/entities/subject_class.py`
- [ ] Protocol `SubjectClassRepository` criado em `src/modules/subject_class/domain/repositories/subject_class_repository.py`
- [ ] Mapper `SubjectClassMapper` criado em `src/modules/subject_class/infra/mappers/subject_class_mapper.py`
- [ ] `SubjectClassSQLAlchemyRepository` criado em `src/modules/subject_class/infra/repositories/`
- [ ] `CreateSubjectClassUseCase` implementado e testado
- [ ] `GetSubjectClassUseCase` implementado e testado
- [ ] `ListSubjectClassesUseCase` implementado e testado
- [ ] `UpdateSubjectClassUseCase` implementado e testado (incluindo troca de `room_id`)
- [ ] `DeleteSubjectClassUseCase` implementado e testado (soft delete)
- [ ] Schemas Pydantic criados em `src/modules/subject_class/interface/schemas/subject_class_schemas.py`
- [ ] Router criado em `src/modules/subject_class/interface/router.py`
- [ ] Router registrado em `src/main.py`
- [ ] `FakeSubjectClassRepository` criado em `tests/unit/fakes/fake_subject_class_repository.py`
- [ ] Testes unitários de use cases escritos e passando
- [ ] Testes de integração do repositório SQLAlchemy escritos e passando
- [ ] Testes E2E do router escritos e passando
- [ ] `uv run pytest` — todos os testes passando sem erros
