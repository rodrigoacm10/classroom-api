# Task 5 — Módulo de Matrícula em Turmas (`SubjectClassEnrollment`)

> **Objetivo**: Implementar o sistema de matrícula de alunos em turmas (`SubjectClass`).
> A matrícula vincula um **membro ativo do tenant com papel `ALUNO`** a uma turma específica.
> Quando a role de um membro muda de `ALUNO` para qualquer outro papel, todas as suas
> matrículas ativas naquele tenant passam automaticamente para `dropped`.
>
> **Entrega esperada**:
> - `POST /tenants/{tenant_id}/subject-classes/{subject_class_id}/enrollments` — matricular aluno
> - `GET /tenants/{tenant_id}/subject-classes/{subject_class_id}/enrollments` — listar matriculados
> - `PATCH /tenants/{tenant_id}/subject-classes/{subject_class_id}/enrollments/{enrollment_id}` — mudar status
> - `DELETE /tenants/{tenant_id}/subject-classes/{subject_class_id}/enrollments/{enrollment_id}` — cancelar matrícula (soft delete)

---

## Conceito central — Vínculo via `TenantMember`

A matrícula **não** aponta para `users.id` diretamente — ela aponta para `tenant_members.id`.

### Por quê `tenant_member_id` e não `user_id`?

| Critério | `user_id → users.id` | `tenant_member_id → tenant_members.id` |
|---|---|---|
| Carrega contexto de tenant | ❌ | ✅ (tenant_members já tem tenant_id) |
| Garante que o usuário é membro do tenant | ❌ (só na aplicação) | ✅ (enforçado pela FK) |
| Permite verificar a role sem join extra | ❌ | ✅ (tenant_members já tem role) |
| Granularidade de matrícula | Por usuário genérico | Por usuário **naquele contexto de tenant** |

**Regra de negócio**: um `TenantMember` só pode ser matriculado se:
1. Seu `role` for `ALUNO` no momento da matrícula.
2. O `tenant_id` do `TenantMember` for igual ao `tenant_id` da `SubjectClass`.
3. Ainda não houver matrícula ativa (`status = active`) para esse par `(subject_class_id, tenant_member_id)`.

---

## Diagrama de relacionamentos

```
tenant_members
  ├── id           ← PK
  ├── tenant_id    → FK tenants.id
  ├── user_id      → FK users.id
  └── role         (ADMIN | PROFESSOR | ALUNO)

subject_classes
  ├── id           ← PK
  └── tenant_id    → FK tenants.id  (deve ser igual ao tenant_id do tenant_member)

subject_class_enrollments
  ├── id                ← PK
  ├── subject_class_id  → FK subject_classes.id  ON DELETE CASCADE
  ├── tenant_member_id  → FK tenant_members.id   ON DELETE CASCADE
  ├── status            ENUM (active | dropped)  DEFAULT active
  └── enrolled_at       TIMESTAMPTZ DEFAULT now()

UNIQUE(subject_class_id, tenant_member_id)  ← evita matrícula duplicada
```

> **Atenção**: A constraint `UNIQUE(subject_class_id, tenant_member_id)` garante que um
> mesmo aluno não pode ser matriculado duas vezes na mesma turma ao mesmo tempo.
> Para reabilitar um aluno que havia sido `dropped`, o use case deve alterar o `status`
> de volta para `active` em vez de criar um novo registro.

---

## Status da Matrícula — Enum `EnrollmentStatus`

```python
# src/shared/enums/enrollment_status.py
from enum import Enum

class EnrollmentStatus(str, Enum):
    ACTIVE = "active"
    DROPPED = "dropped"
```

| Status | Descrição |
|---|---|
| `active` | Aluno está regularmente matriculado na turma |
| `dropped` | Matrícula cancelada (manual pelo ADMIN ou automática por mudança de role) |

> **Nota**: Não há `deleted` neste modelo — o histórico de matrículas deve ser preservado.
> Em vez de soft delete, o status `dropped` cumpre esse papel. A API de `DELETE` apenas
> muda o status para `dropped`.

---

## Regra de Negócio Crítica — Mudança de Role

### Gatilho
Quando o `UpdateTenantMemberRoleUseCase` altera a role de um membro de `ALUNO` para
qualquer outro papel (`PROFESSOR` ou `ADMIN`), deve-se:

1. Buscar todas as matrículas ativas (`status = active`) do `tenant_member_id` afetado.
2. Alterar o status de **todas** elas para `dropped`.
3. Persistir as mudanças **na mesma transação** da mudança de role.

### Fluxo de chamada (diagrama)

```
[ADMIN] PATCH /tenants/{id}/members/{user_id}/role
        │
        ▼
UpdateTenantMemberRoleUseCase.execute()
        │
        ├── [1] Verifica se a tenant existe
        ├── [2] Busca o TenantMember ativo
        ├── [3] Verifica se a role está mudando
        ├── [4] Se era ADMIN, valida se não é o único admin
        ├── [5] Atualiza member.role = new_role
        │
        └── [6] SE old_role == ALUNO E new_role != ALUNO:
                    EnrollmentRepository.drop_all_active_for_member(tenant_member_id)
                    ↓
                    UPDATE subject_class_enrollments
                    SET status = 'dropped'
                    WHERE tenant_member_id = ? AND status = 'active'
```

> **Por que na mesma transação?** Garantir atomicidade: não pode existir um membro com
> papel `PROFESSOR` que ainda tem matrículas `active` como aluno. Se a transação falhar,
> nenhuma alteração é persistida.

---

## Controle de Erros (exceções esperadas)

| Situação | Exceção | Código HTTP |
|---|---|---|
| Turma não encontrada ou `deleted=True` | `ResourceNotFoundException` | `404` |
| Tenant não encontrada ou deletada | `ResourceNotFoundException` | `404` |
| `TenantMember` não encontrado ou `deleted=True` | `ResourceNotFoundException` | `404` |
| `TenantMember.role != ALUNO` no momento da matrícula | `BusinessRuleException` | `400` |
| `TenantMember.tenant_id != SubjectClass.tenant_id` | `BusinessRuleException` | `400` |
| Matrícula já existente (`status = active`) | `BusinessRuleException` | `409` |
| Matrícula não encontrada | `ResourceNotFoundException` | `404` |
| Usuário sem permissão (ALUNO tentando matricular outro aluno) | `ForbiddenException` | `403` |
| Validação de schema Pydantic | `ValidationError` | `422` |

---

## Visão geral da ordem de implementação

```
shared/enums/enrollment_status.py                          ← 1. Enum EnrollmentStatus
infra/database/models/enrollment.py                        ← 2. Model SQLAlchemy EnrollmentModel
alembic/versions/XXX_create_subject_class_enrollments.py   ← 3. Migration
modules/enrollment/
  domain/entities/enrollment.py                            ← 4. Entidade de domínio Enrollment
  domain/repositories/enrollment_repository.py             ← 5. Protocol do repositório
  infra/mappers/enrollment_mapper.py                       ← 6. Mapper Model ↔ Entity
  infra/repositories/enrollment_sqlalchemy_repository.py   ← 7. Implementação SQLAlchemy
  application/use_cases/enroll_student.py                  ← 8. EnrollStudentUseCase
  application/use_cases/list_enrollments.py                ← 9. ListEnrollmentsUseCase
  application/use_cases/update_enrollment_status.py        ← 10. UpdateEnrollmentStatusUseCase
  application/use_cases/drop_enrollment.py                 ← 11. DropEnrollmentUseCase
  interface/schemas/enrollment_schemas.py                  ← 12. Schemas Pydantic
  interface/router.py                                      ← 13. Router HTTP com 4 rotas
modules/tenant/application/use_cases/update_tenant_member_role.py  ← 14. Modificar para chamar drop_all_active_for_member
main.py                                                    ← 15. Registrar o router
tests/                                                     ← 16. Testes unitários, integração e E2E
```

---

## Passo 1 — Enum `EnrollmentStatus`

```python
# src/shared/enums/enrollment_status.py
from enum import Enum


class EnrollmentStatus(str, Enum):
    ACTIVE = "active"
    DROPPED = "dropped"
```

---

## Passo 2 — Model SQLAlchemy `EnrollmentModel`

```python
# src/infra/database/models/enrollment.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infra.database.base import Base
from shared.enums.enrollment_status import EnrollmentStatus


class EnrollmentModel(Base):
    __tablename__ = "subject_class_enrollments"
    __table_args__ = (
        UniqueConstraint(
            "subject_class_id",
            "tenant_member_id",
            name="uq_enrollment_class_member",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subject_class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subject_classes.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_members.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        Enum(EnrollmentStatus, name="enrollment_status", create_type=True),
        default=EnrollmentStatus.ACTIVE,
        nullable=False,
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

> **Notas de design:**
> - `ON DELETE CASCADE` em ambas as FKs — se a turma ou o membro for removido do banco,
>   as matrículas relacionadas são removidas automaticamente.
> - O `status` assume `ACTIVE` por padrão. Não há coluna `deleted` — o `dropped` cumpre
>   esse papel, preservando o histórico.
> - A `UniqueConstraint` garante no banco que não existam duas matrículas para o mesmo
>   par `(subject_class_id, tenant_member_id)`.

---

## Passo 3 — Migration Alembic

```bash
uv run alembic revision --autogenerate -m "create subject_class_enrollments table"
uv run alembic upgrade head
```

SQL gerado aproximadamente:

```sql
CREATE TYPE enrollment_status AS ENUM ('active', 'dropped');

CREATE TABLE subject_class_enrollments (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_class_id  UUID NOT NULL REFERENCES subject_classes(id) ON DELETE CASCADE,
    tenant_member_id  UUID NOT NULL REFERENCES tenant_members(id) ON DELETE CASCADE,
    status            enrollment_status NOT NULL DEFAULT 'active',
    enrolled_at       TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_enrollment_class_member UNIQUE (subject_class_id, tenant_member_id)
);

CREATE INDEX idx_enrollments_subject_class_id ON subject_class_enrollments(subject_class_id);
CREATE INDEX idx_enrollments_tenant_member_id ON subject_class_enrollments(tenant_member_id);
```

---

## Passo 4 — Entidade de Domínio `Enrollment`

```python
# src/modules/enrollment/domain/entities/enrollment.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from shared.enums.enrollment_status import EnrollmentStatus


@dataclass
class Enrollment:
    subject_class_id: UUID
    tenant_member_id: UUID
    status: EnrollmentStatus = EnrollmentStatus.ACTIVE
    id: UUID = field(default_factory=uuid4)
    enrolled_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## Passo 5 — Interface do Repositório (Protocol)

```python
# src/modules/enrollment/domain/repositories/enrollment_repository.py
from typing import Protocol
from uuid import UUID

from modules.enrollment.domain.entities.enrollment import Enrollment
from shared.enums.enrollment_status import EnrollmentStatus


class EnrollmentRepository(Protocol):

    async def save(self, enrollment: Enrollment) -> Enrollment: ...

    async def find_by_id(self, enrollment_id: UUID) -> Enrollment | None: ...

    async def find_by_class_and_member(
        self, subject_class_id: UUID, tenant_member_id: UUID
    ) -> Enrollment | None: ...

    async def list_by_subject_class(
        self, subject_class_id: UUID, status: EnrollmentStatus | None = None
    ) -> list[Enrollment]: ...

    async def drop_all_active_for_member(self, tenant_member_id: UUID) -> int:
        """
        Altera o status de todas as matrículas ativas de um tenant_member para DROPPED.
        Retorna o número de matrículas afetadas.
        Chamado pelo UpdateTenantMemberRoleUseCase quando a role muda de ALUNO.
        """
        ...
```

---

## Passo 6 — Mapper `EnrollmentMapper`

```python
# src/modules/enrollment/infra/mappers/enrollment_mapper.py
from infra.database.models.enrollment import EnrollmentModel
from modules.enrollment.domain.entities.enrollment import Enrollment


class EnrollmentMapper:

    @staticmethod
    def to_domain(model: EnrollmentModel) -> Enrollment:
        return Enrollment(
            id=model.id,
            subject_class_id=model.subject_class_id,
            tenant_member_id=model.tenant_member_id,
            status=model.status,
            enrolled_at=model.enrolled_at,
        )

    @staticmethod
    def to_model(entity: Enrollment) -> EnrollmentModel:
        return EnrollmentModel(
            id=entity.id,
            subject_class_id=entity.subject_class_id,
            tenant_member_id=entity.tenant_member_id,
            status=entity.status,
            enrolled_at=entity.enrolled_at,
        )
```

---

## Passo 7 — Repositório SQLAlchemy `EnrollmentSQLAlchemyRepository`

```python
# src/modules/enrollment/infra/repositories/enrollment_sqlalchemy_repository.py
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.enrollment import EnrollmentModel
from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.enrollment.infra.mappers.enrollment_mapper import EnrollmentMapper
from shared.enums.enrollment_status import EnrollmentStatus


class EnrollmentSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, enrollment: Enrollment) -> Enrollment:
        model = EnrollmentMapper.to_model(enrollment)
        merged = await self.session.merge(model)
        await self.session.commit()
        await self.session.refresh(merged)
        return EnrollmentMapper.to_domain(merged)

    async def find_by_id(self, enrollment_id: UUID) -> Enrollment | None:
        stmt = select(EnrollmentModel).where(EnrollmentModel.id == enrollment_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return EnrollmentMapper.to_domain(model) if model else None

    async def find_by_class_and_member(
        self, subject_class_id: UUID, tenant_member_id: UUID
    ) -> Enrollment | None:
        stmt = select(EnrollmentModel).where(
            EnrollmentModel.subject_class_id == subject_class_id,
            EnrollmentModel.tenant_member_id == tenant_member_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return EnrollmentMapper.to_domain(model) if model else None

    async def list_by_subject_class(
        self, subject_class_id: UUID, status: EnrollmentStatus | None = None
    ) -> list[Enrollment]:
        stmt = select(EnrollmentModel).where(
            EnrollmentModel.subject_class_id == subject_class_id
        )
        if status is not None:
            stmt = stmt.where(EnrollmentModel.status == status)
        result = await self.session.execute(stmt)
        return [EnrollmentMapper.to_domain(m) for m in result.scalars().all()]

    async def drop_all_active_for_member(self, tenant_member_id: UUID) -> int:
        """
        UPDATE subject_class_enrollments
        SET status = 'dropped'
        WHERE tenant_member_id = :id AND status = 'active'
        """
        stmt = (
            update(EnrollmentModel)
            .where(
                EnrollmentModel.tenant_member_id == tenant_member_id,
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
            )
            .values(status=EnrollmentStatus.DROPPED)
            .returning(EnrollmentModel.id)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return len(result.fetchall())
```

---

## Passo 8 — Casos de Uso

### 8.1 `EnrollStudentUseCase`

```python
# src/modules/enrollment/application/use_cases/enroll_student.py
from dataclasses import dataclass
from uuid import UUID

from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class EnrollStudentInput:
    subject_class_id: UUID
    tenant_member_id: UUID
    tenant_id: UUID  # do contexto da request — para validação cruzada


class EnrollStudentUseCase:

    def __init__(
        self,
        enrollment_repo: EnrollmentRepository,
        subject_class_repo: SubjectClassRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.enrollment_repo = enrollment_repo
        self.subject_class_repo = subject_class_repo
        self.member_repo = member_repo

    async def execute(self, data: EnrollStudentInput) -> Enrollment:
        # 1. Verifica se a turma existe e não foi deletada
        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            subject_class_id=data.subject_class_id,
            tenant_id=data.tenant_id,
        )
        if not subject_class:
            raise ResourceNotFoundException("Turma não encontrada.")

        # 2. Busca o TenantMember
        member = await self.member_repo.find_by_id(data.tenant_member_id, include_deleted=False)
        if not member:
            raise ResourceNotFoundException("Membro não encontrado.")

        # 3. Valida que o membro pertence ao mesmo tenant da turma
        if member.tenant_id != data.tenant_id:
            raise BusinessRuleException("O membro não pertence a esta instituição.")

        # 4. Valida que o membro tem papel ALUNO
        if member.role != UserRole.ALUNO:
            raise BusinessRuleException(
                "Apenas alunos podem ser matriculados em turmas. "
                f"O membro possui papel '{member.role.value}'."
            )

        # 5. Verifica se já existe matrícula (em qualquer status) para evitar duplicata
        existing = await self.enrollment_repo.find_by_class_and_member(
            subject_class_id=data.subject_class_id,
            tenant_member_id=data.tenant_member_id,
        )
        if existing:
            if existing.status == EnrollmentStatus.ACTIVE:
                raise BusinessRuleException("O aluno já está matriculado nesta turma.")
            # Se dropped, reativa a matrícula
            existing.status = EnrollmentStatus.ACTIVE
            return await self.enrollment_repo.save(existing)

        # 6. Cria nova matrícula
        enrollment = Enrollment(
            subject_class_id=data.subject_class_id,
            tenant_member_id=data.tenant_member_id,
        )
        return await self.enrollment_repo.save(enrollment)
```

> **Detalhe importante do passo 5**: Se o aluno já tinha uma matrícula `dropped` (foi
> cancelada anteriormente), ao invés de criar um registro duplicado (violando a UNIQUE
> constraint), o use case **reativa** a matrícula existente alterando o status para `active`.

### 8.2 `DropEnrollmentUseCase`

```python
# src/modules/enrollment/application/use_cases/drop_enrollment.py
from dataclasses import dataclass
from uuid import UUID

from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository
from shared.enums.enrollment_status import EnrollmentStatus
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class DropEnrollmentInput:
    enrollment_id: UUID
    subject_class_id: UUID  # para validação cruzada


class DropEnrollmentUseCase:

    def __init__(self, enrollment_repo: EnrollmentRepository) -> None:
        self.enrollment_repo = enrollment_repo

    async def execute(self, data: DropEnrollmentInput) -> None:
        enrollment = await self.enrollment_repo.find_by_id(data.enrollment_id)
        if not enrollment or enrollment.subject_class_id != data.subject_class_id:
            raise ResourceNotFoundException("Matrícula não encontrada.")

        if enrollment.status == EnrollmentStatus.DROPPED:
            raise BusinessRuleException("Matrícula já está cancelada.")

        enrollment.status = EnrollmentStatus.DROPPED
        await self.enrollment_repo.save(enrollment)
```

### 8.3 `ListEnrollmentsUseCase`

```python
# src/modules/enrollment/application/use_cases/list_enrollments.py
from dataclasses import dataclass
from uuid import UUID

from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from shared.enums.enrollment_status import EnrollmentStatus
from shared.exceptions import ResourceNotFoundException


@dataclass
class ListEnrollmentsInput:
    subject_class_id: UUID
    tenant_id: UUID
    status: EnrollmentStatus | None = None  # None = todos os status


class ListEnrollmentsUseCase:

    def __init__(
        self,
        enrollment_repo: EnrollmentRepository,
        subject_class_repo: SubjectClassRepository,
    ) -> None:
        self.enrollment_repo = enrollment_repo
        self.subject_class_repo = subject_class_repo

    async def execute(self, data: ListEnrollmentsInput) -> list[Enrollment]:
        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            subject_class_id=data.subject_class_id,
            tenant_id=data.tenant_id,
        )
        if not subject_class:
            raise ResourceNotFoundException("Turma não encontrada.")

        return await self.enrollment_repo.list_by_subject_class(
            subject_class_id=data.subject_class_id,
            status=data.status,
        )
```

---

## Passo 9 — Modificar `UpdateTenantMemberRoleUseCase`

O use case existente em `update_tenant_member_role.py` deve receber o `EnrollmentRepository`
e chamar `drop_all_active_for_member` quando a role sai de `ALUNO`:

```python
# Adicionar ao UpdateTenantMemberRoleUseCase:

from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository

class UpdateTenantMemberRoleUseCase:

    def __init__(
        self,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
        enrollment_repo: EnrollmentRepository,  # ← NOVO
    ) -> None:
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo
        self.enrollment_repo = enrollment_repo   # ← NOVO

    async def execute(self, data: UpdateTenantMemberRoleInput) -> TenantMember:
        # ... (lógica existente dos passos 1-4) ...

        old_role = member.role  # ← guardar antes de alterar

        # 5. Atualiza a role e persiste
        member.role = data.new_role
        updated_member = await self.member_repo.save(member)

        # 6. Se a role anterior era ALUNO e a nova não é ALUNO,
        #    cancela todas as matrículas ativas desse membro  ← NOVO
        if old_role == UserRole.ALUNO and data.new_role != UserRole.ALUNO:
            dropped_count = await self.enrollment_repo.drop_all_active_for_member(
                tenant_member_id=member.id
            )
            # dropped_count pode ser usado para logging/observabilidade

        return updated_member
```

> **Atomicidade**: O `drop_all_active_for_member` faz um `UPDATE ... WHERE` em batch
> (uma única instrução SQL), o que é mais eficiente e mais seguro do que iterar
> matrícula por matrícula. O `commit` é feito dentro do método do repositório.

---

## Passo 10 — Schemas Pydantic

```python
# src/modules/enrollment/interface/schemas/enrollment_schemas.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from shared.enums.enrollment_status import EnrollmentStatus


class EnrollStudentRequest(BaseModel):
    tenant_member_id: UUID


class EnrollmentResponse(BaseModel):
    id: UUID
    subject_class_id: UUID
    tenant_member_id: UUID
    status: EnrollmentStatus
    enrolled_at: datetime

    model_config = {"from_attributes": True}
```

---

## Passo 11 — Router FastAPI

```python
# src/modules/enrollment/interface/router.py
router = APIRouter(
    prefix="/tenants/{tenant_id}/subject-classes/{subject_class_id}/enrollments",
    tags=["enrollments"],
)

@router.post("", response_model=EnrollmentResponse, status_code=201,
             dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))])
async def enroll_student(tenant_id, subject_class_id, body: EnrollStudentRequest, ...):
    """Matricula um aluno (TenantMember com role ALUNO) em uma turma."""

@router.get("", response_model=list[EnrollmentResponse])
async def list_enrollments(tenant_id, subject_class_id, status: EnrollmentStatus | None = None, ...):
    """Lista matriculados da turma. ADMIN e PROFESSOR podem filtrar por status."""

@router.delete("/{enrollment_id}", status_code=204,
               dependencies=[Depends(require_role(UserRole.ADMIN))])
async def drop_enrollment(tenant_id, subject_class_id, enrollment_id, ...):
    """Cancela matrícula (status → dropped). Apenas ADMIN."""
```

---

## Passo 12 — Testes

### 12.1 Cenários de Teste Unitários

| Caso | Use Case | Resultado esperado |
|---|---|---|
| Matricular aluno válido | `EnrollStudentUseCase` | Retorna `Enrollment` com `status=active` |
| Matricular membro com role `PROFESSOR` | `EnrollStudentUseCase` | Lança `BusinessRuleException` |
| Matricular membro de outro tenant | `EnrollStudentUseCase` | Lança `BusinessRuleException` |
| Matricular aluno já ativo na turma | `EnrollStudentUseCase` | Lança `BusinessRuleException` |
| Matricular aluno que havia sido `dropped` | `EnrollStudentUseCase` | Reativa a matrícula (`status=active`) |
| Matricular em turma deletada | `EnrollStudentUseCase` | Lança `ResourceNotFoundException` |
| Cancelar matrícula ativa | `DropEnrollmentUseCase` | `status=dropped` |
| Cancelar matrícula já `dropped` | `DropEnrollmentUseCase` | Lança `BusinessRuleException` |
| Listar matrículas ativas | `ListEnrollmentsUseCase` | Retorna apenas `status=active` |
| Listar todas (sem filtro de status) | `ListEnrollmentsUseCase` | Retorna todos os status |
| Mudança de role ALUNO→PROFESSOR | `UpdateTenantMemberRoleUseCase` | Todas as matrículas ativas → `dropped` |
| Mudança de role PROFESSOR→ALUNO | `UpdateTenantMemberRoleUseCase` | Nenhuma matrícula afetada |

### 12.2 Cenários de Teste E2E

| Caso | Rota | Status esperado |
|---|---|---|
| Matricular aluno (ADMIN) | `POST .../enrollments` | `201` |
| Matricular aluno (PROFESSOR) | `POST .../enrollments` | `201` |
| Matricular aluno (ALUNO tentando matricular outro) | `POST .../enrollments` | `403` |
| Matricular membro com role PROFESSOR | `POST .../enrollments` | `400` |
| Matricular duas vezes o mesmo aluno | `POST .../enrollments` | `409` |
| Listar matriculados | `GET .../enrollments` | `200` |
| Filtrar por `status=active` | `GET .../enrollments?status=active` | `200` |
| Cancelar matrícula (ADMIN) | `DELETE .../enrollments/{id}` | `204` |
| Cancelar matrícula (PROFESSOR) | `DELETE .../enrollments/{id}` | `403` |
| Aluno aparece em listagem após matrícula | `GET .../enrollments` | `200` (contém o aluno) |
| Aluno NÃO aparece com `status=active` após `drop` | `GET .../enrollments?status=active` | `200` (sem o aluno) |
| Mudança de role → matrículas ficam `dropped` | `PATCH .../members/role` + `GET .../enrollments` | `200` (status=dropped) |

---

## Checklist de implementação

- [ ] Enum `EnrollmentStatus` criado em `src/shared/enums/enrollment_status.py`
- [ ] Model `EnrollmentModel` criado em `src/infra/database/models/enrollment.py`
- [ ] `EnrollmentModel` registrado em `src/infra/database/models/__init__.py`
- [ ] Migration gerada e aplicada
- [ ] Entidade `Enrollment` criada em `src/modules/enrollment/domain/entities/enrollment.py`
- [ ] Protocol `EnrollmentRepository` criado (com método `drop_all_active_for_member`)
- [ ] Mapper `EnrollmentMapper` criado
- [ ] `EnrollmentSQLAlchemyRepository` criado (com `UPDATE ... WHERE` em batch)
- [ ] `EnrollStudentUseCase` implementado (com lógica de reativação de matrícula dropped)
- [ ] `ListEnrollmentsUseCase` implementado
- [ ] `DropEnrollmentUseCase` implementado
- [ ] `UpdateTenantMemberRoleUseCase` modificado para chamar `drop_all_active_for_member`
- [ ] Schemas Pydantic criados
- [ ] Router criado e registrado em `main.py`
- [ ] Testes unitários escritos e passando (incluindo cenário de mudança de role)
- [ ] Testes E2E escritos e passando
- [ ] `uv run pytest` — todos os testes passando sem erros
