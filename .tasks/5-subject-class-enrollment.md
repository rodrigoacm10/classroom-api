# Task 5 — Módulo de Matrícula em Turmas (`SubjectClassEnrollment`)

> **Objetivo**: Implementar o sistema de matrícula de alunos em turmas (`SubjectClass`).
> A matrícula vincula um **membro ativo do tenant com papel `ALUNO`** a uma turma específica.
> Quando a role de um membro muda de `ALUNO` para qualquer outro papel, todas as suas
> matrículas ativas naquele tenant passam automaticamente para `dropped`.
>
> **Entrega esperada**:
> - `POST /tenants/{tenant_id}/subject-classes/{subject_class_id}/enrollments` — matricular aluno
> - `GET /tenants/{tenant_id}/subject-classes/{subject_class_id}/enrollments` — listar matriculados
> - `PATCH /tenants/{tenant_id}/subject-classes/{subject_class_id}/enrollments/{enrollment_id}` — cancelar matrícula (status → dropped)
> - `DELETE /tenants/{tenant_id}/subject-classes/{subject_class_id}/enrollments/{enrollment_id}` — remover matrícula (soft delete para correção de erro, ADMIN only)

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
  ├── deleted           BOOLEAN                  DEFAULT false
  └── enrolled_at       TIMESTAMPTZ DEFAULT now()

UNIQUE (subject_class_id, tenant_member_id) WHERE deleted = false  ← partial unique index
```

> **Atenção**: A unicidade é garantida por um **partial unique index** que considera apenas
> registros com `deleted=false`. Isso resolve um problema crítico de design:
> uma `UniqueConstraint` simples em `(subject_class_id, tenant_member_id)` bloquearia
> a criação de um novo registro mesmo após um soft delete, pois o banco enxerga a linha
> deletada. Com o índice parcial, registros com `deleted=true` são ignorados pela constraint,
> permitindo nova matrícula após correção de erro.
>
> | Cenário | Comportamento |
> |---|---|
> | Aluno `active` na turma → tenta matricular novamente | Bloqueado pelo índice parcial (409) |
> | Aluno `dropped` → tenta matricular novamente | Permitido pelo banco — use case reativa o registro |
> | Aluno `deleted=True` → tenta matricular novamente | Permitido pelo banco — use case cria novo registro |

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
| `dropped` | Matrícula cancelada — evento de negócio legítimo (aluno cancelou, role foi alterada) |

---

## Soft Delete vs. Status `dropped` — Distinção Semântica

Este modelo possui **dois mecanismos** de "remover" uma matrícula, com semânticas completamente diferentes:

| Mecanismo | Campo | Quem aciona | Semântica | Aparece no histórico? |
|---|---|---|---|---|
| **Soft delete** | `deleted = True` | ADMIN | Correção de erro — o aluno nunca deveria ter sido matriculado | ❌ Some de todas as views |
| **Cancelamento** | `status = dropped` | ADMIN via PATCH, ou automático por mudança de role | Evento legítimo do ciclo de vida da matrícula | ✅ Preservado no histórico |

### Por que essa distinção importa?

- Um aluno que se matriculou, frequentou aulas e depois cancelou é **diferente** de um aluno adicionado por engano.
- `dropped` entra em relatórios de frequência, histórico acadêmico e auditoria.
- `deleted=True` equivale a "este registro não deveria existir" — invisível para qualquer query normal.
- Sistemas como **Canvas LMS** e **edX** fazem exatamente essa distinção: possuem um estado `deleted` separado dos estados de ciclo de vida (`inactive`, `completed`, `rejected`).

### Regras de visibilidade

| Query | Condição SQL |
|---|---|
| Listagem padrão (alunos ativos) | `WHERE deleted=false AND status='active'` |
| Histórico de matrículas (inclui cancelamentos) | `WHERE deleted=false` |
| Relatório completo com ADMIN (`include_deleted=true`) | sem filtro de `deleted` |

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
infra/database/models/enrollment.py                        ← 2. Model SQLAlchemy EnrollmentModel (com deleted + status)
alembic/versions/XXX_create_subject_class_enrollments.py   ← 3. Migration
modules/enrollment/
  domain/entities/enrollment.py                            ← 4. Entidade de domínio Enrollment
  domain/repositories/enrollment_repository.py             ← 5. Protocol do repositório (com include_deleted)
  infra/mappers/enrollment_mapper.py                       ← 6. Mapper Model ↔ Entity
  infra/repositories/enrollment_sqlalchemy_repository.py   ← 7. Implementação SQLAlchemy
  application/use_cases/enroll_student.py                  ← 8. EnrollStudentUseCase
  application/use_cases/list_enrollments.py                ← 9. ListEnrollmentsUseCase
  application/use_cases/drop_enrollment.py                 ← 10. DropEnrollmentUseCase (PATCH → status=dropped)
  application/use_cases/delete_enrollment.py               ← 11. DeleteEnrollmentUseCase (DELETE → deleted=True)
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

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, false, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infra.database.base import Base
from shared.enums.enrollment_status import EnrollmentStatus


class EnrollmentModel(Base):
    __tablename__ = "subject_class_enrollments"
    __table_args__ = (
        # Partial unique index — garante unicidade APENAS em registros não deletados.
        # Uma UniqueConstraint simples bloquearia nova matrícula mesmo após soft delete,
        # pois o banco ainda enxerga a linha com deleted=True.
        Index(
            "uq_enrollment_active",
            "subject_class_id",
            "tenant_member_id",
            unique=True,
            postgresql_where=text("deleted = false"),
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
    deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

> **Notas de design:**
> - `ON DELETE CASCADE` em ambas as FKs — se a turma ou o membro for removido do banco,
>   as matrículas relacionadas são removidas automaticamente.
> - `deleted` serve para **correção de erro** (ADMIN removeu um aluno adicionado indevidamente).
>   Registros com `deleted=True` são invisíveis em todas as queries normais.
> - `status=dropped` serve para **eventos legítimos de cancelamento** — o histórico é preservado.
> - O **partial unique index** `uq_enrollment_active` (com `WHERE deleted=false`) garante
>   unicidade apenas em registros ativos. Registros com `deleted=True` são transparentes
>   para a constraint, permitindo nova matrícula após correção de erro — comportamento
>   **impossível** com uma `UniqueConstraint` simples.

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
    deleted           BOOLEAN NOT NULL DEFAULT false,
    enrolled_at       TIMESTAMPTZ DEFAULT now()
);

-- Partial unique index: garante unicidade apenas em registros não deletados.
-- Diferente de UNIQUE CONSTRAINT, não bloqueia nova matrícula após soft delete.
CREATE UNIQUE INDEX uq_enrollment_active
    ON subject_class_enrollments(subject_class_id, tenant_member_id)
    WHERE deleted = false;

CREATE INDEX idx_enrollments_subject_class_id ON subject_class_enrollments(subject_class_id);
CREATE INDEX idx_enrollments_tenant_member_id ON subject_class_enrollments(tenant_member_id);
```

> **⚠️ Atenção com autogenerate**: O Alembic pode não detectar o `Index` com
> `postgresql_where` automaticamente dependendo da versão. Verifique a migration gerada
> e adicione manualmente se necessário:
> ```python
> # Na migration gerada:
> op.create_index(
>     "uq_enrollment_active",
>     "subject_class_enrollments",
>     ["subject_class_id", "tenant_member_id"],
>     unique=True,
>     postgresql_where=sa.text("deleted = false"),
> )
> ```

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
    deleted: bool = False
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

    async def find_by_id(
        self, enrollment_id: UUID, include_deleted: bool = False
    ) -> Enrollment | None: ...

    async def find_by_class_and_member(
        self,
        subject_class_id: UUID,
        tenant_member_id: UUID,
        include_deleted: bool = False,
    ) -> Enrollment | None: ...

    async def list_by_subject_class(
        self,
        subject_class_id: UUID,
        status: EnrollmentStatus | None = None,
        include_deleted: bool = False,
    ) -> list[Enrollment]: ...

    async def drop_all_active_for_member(self, tenant_member_id: UUID) -> int:
        """
        Altera o status de todas as matrículas ativas (e não deletadas) de um tenant_member para DROPPED.
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
            deleted=model.deleted,
            enrolled_at=model.enrolled_at,
        )

    @staticmethod
    def to_model(entity: Enrollment) -> EnrollmentModel:
        return EnrollmentModel(
            id=entity.id,
            subject_class_id=entity.subject_class_id,
            tenant_member_id=entity.tenant_member_id,
            status=entity.status,
            deleted=entity.deleted,
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

    async def find_by_id(
        self, enrollment_id: UUID, include_deleted: bool = False
    ) -> Enrollment | None:
        stmt = select(EnrollmentModel).where(EnrollmentModel.id == enrollment_id)
        if not include_deleted:
            stmt = stmt.where(EnrollmentModel.deleted.is_(False))
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return EnrollmentMapper.to_domain(model) if model else None

    async def find_by_class_and_member(
        self,
        subject_class_id: UUID,
        tenant_member_id: UUID,
        include_deleted: bool = False,
    ) -> Enrollment | None:
        stmt = select(EnrollmentModel).where(
            EnrollmentModel.subject_class_id == subject_class_id,
            EnrollmentModel.tenant_member_id == tenant_member_id,
        )
        if not include_deleted:
            stmt = stmt.where(EnrollmentModel.deleted.is_(False))
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return EnrollmentMapper.to_domain(model) if model else None

    async def list_by_subject_class(
        self,
        subject_class_id: UUID,
        status: EnrollmentStatus | None = None,
        include_deleted: bool = False,
    ) -> list[Enrollment]:
        stmt = select(EnrollmentModel).where(
            EnrollmentModel.subject_class_id == subject_class_id
        )
        if not include_deleted:
            stmt = stmt.where(EnrollmentModel.deleted.is_(False))
        if status is not None:
            stmt = stmt.where(EnrollmentModel.status == status)
        result = await self.session.execute(stmt)
        return [EnrollmentMapper.to_domain(m) for m in result.scalars().all()]

    async def drop_all_active_for_member(self, tenant_member_id: UUID) -> int:
        """
        UPDATE subject_class_enrollments
        SET status = 'dropped'
        WHERE tenant_member_id = :id AND status = 'active' AND deleted = false
        """
        stmt = (
            update(EnrollmentModel)
            .where(
                EnrollmentModel.tenant_member_id == tenant_member_id,
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                EnrollmentModel.deleted.is_(False),
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

        # 5. Verifica se já existe matrícula ATIVA (não deletada) para evitar duplicata
        existing = await self.enrollment_repo.find_by_class_and_member(
            subject_class_id=data.subject_class_id,
            tenant_member_id=data.tenant_member_id,
            include_deleted=False,  # ignora registros deletados (erros corrigidos)
        )
        if existing:
            if existing.status == EnrollmentStatus.ACTIVE:
                raise BusinessRuleException("O aluno já está matriculado nesta turma.")
            # Se dropped, reativa a matrícula (cancelamento anterior, não um erro)
            existing.status = EnrollmentStatus.ACTIVE
            return await self.enrollment_repo.save(existing)

        # 6. Cria nova matrícula
        enrollment = Enrollment(
            subject_class_id=data.subject_class_id,
            tenant_member_id=data.tenant_member_id,
        )
        return await self.enrollment_repo.save(enrollment)
```

> **Detalhe importante do passo 5**: Se o aluno já tinha uma matrícula `dropped` (cancelamento legítimo),
> o use case **reativa** a matrícula existente (`status → active`), preservando o histórico.
> Se a matrícula anterior foi `deleted=True` (erro corrigido), ela é invisível para essa
> query (`include_deleted=False`) e um novo registro será criado normalmente.

### 8.2 `DropEnrollmentUseCase` (PATCH — cancelamento legítimo)

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
    """Cancela uma matrícula por evento de negócio legítimo (aluno desistiu, ADMIN cancelou).
    Altera o status para DROPPED. O registro é PRESERVADO no histórico.
    Diferente de DeleteEnrollmentUseCase, que realiza soft delete para correção de erros.
    """

    def __init__(self, enrollment_repo: EnrollmentRepository) -> None:
        self.enrollment_repo = enrollment_repo

    async def execute(self, data: DropEnrollmentInput) -> None:
        enrollment = await self.enrollment_repo.find_by_id(data.enrollment_id, include_deleted=False)
        if not enrollment or enrollment.subject_class_id != data.subject_class_id:
            raise ResourceNotFoundException("Matrícula não encontrada.")

        if enrollment.status == EnrollmentStatus.DROPPED:
            raise BusinessRuleException("Matrícula já está cancelada.")

        enrollment.status = EnrollmentStatus.DROPPED
        await self.enrollment_repo.save(enrollment)
```

### 8.3 `DeleteEnrollmentUseCase` (DELETE — correção de erro, ADMIN only)

```python
# src/modules/enrollment/application/use_cases/delete_enrollment.py
from dataclasses import dataclass
from uuid import UUID

from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class DeleteEnrollmentInput:
    enrollment_id: UUID
    subject_class_id: UUID


class DeleteEnrollmentUseCase:
    """Remove uma matrícula por correção de erro administrativo.
    Realiza soft delete (deleted=True). O registro some de TODAS as visualizações normais.
    Diferente de DropEnrollmentUseCase, que preserva o histórico via status=dropped.
    Exclusivo para ADMIN.
    """

    def __init__(self, enrollment_repo: EnrollmentRepository) -> None:
        self.enrollment_repo = enrollment_repo

    async def execute(self, data: DeleteEnrollmentInput) -> None:
        enrollment = await self.enrollment_repo.find_by_id(
            data.enrollment_id, include_deleted=False
        )
        if not enrollment or enrollment.subject_class_id != data.subject_class_id:
            raise ResourceNotFoundException("Matrícula não encontrada.")

        enrollment.deleted = True
        await self.enrollment_repo.save(enrollment)
```

### 8.4 `ListEnrollmentsUseCase`

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
    status: EnrollmentStatus | None = None  # None = todos os status não deletados
    include_deleted: bool = False           # True = apenas ADMIN, para auditoria


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
            include_deleted=data.include_deleted,
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
async def list_enrollments(
    tenant_id, subject_class_id,
    status: EnrollmentStatus | None = None,
    include_deleted: bool = False,  # apenas ADMIN deve usar este parâmetro
    ...
):
    """Lista matriculados da turma. Filtrável por status. ADMIN pode incluir deletados."""

@router.patch("/{enrollment_id}", status_code=204,
              dependencies=[Depends(require_role(UserRole.ADMIN))])
async def drop_enrollment(tenant_id, subject_class_id, enrollment_id, ...):
    """Cancela matrícula por evento legítimo (status → dropped). Histórico preservado. Apenas ADMIN."""

@router.delete("/{enrollment_id}", status_code=204,
               dependencies=[Depends(require_role(UserRole.ADMIN))])
async def delete_enrollment(tenant_id, subject_class_id, enrollment_id, ...):
    """Remove matrícula por erro administrativo (soft delete → deleted=True). Some do histórico. Apenas ADMIN."""
```

---

## Passo 12 — Testes

### 12.1 Cenários de Teste Unitários

| Caso | Use Case | Resultado esperado |
|---|---|---|
| Matricular aluno válido | `EnrollStudentUseCase` | Retorna `Enrollment` com `status=active, deleted=false` |
| Matricular membro com role `PROFESSOR` | `EnrollStudentUseCase` | Lança `BusinessRuleException` |
| Matricular membro de outro tenant | `EnrollStudentUseCase` | Lança `BusinessRuleException` |
| Matricular aluno já ativo na turma | `EnrollStudentUseCase` | Lança `BusinessRuleException` |
| Matricular aluno que havia sido `dropped` | `EnrollStudentUseCase` | Reativa a matrícula (`status=active`) |
| Matricular aluno que havia sido deletado (`deleted=True`) | `EnrollStudentUseCase` | Cria novo registro (o deletado é invisível) |
| Matricular em turma deletada | `EnrollStudentUseCase` | Lança `ResourceNotFoundException` |
| Cancelar matrícula ativa (PATCH) | `DropEnrollmentUseCase` | `status=dropped` — histórico preservado |
| Cancelar matrícula já `dropped` (PATCH) | `DropEnrollmentUseCase` | Lança `BusinessRuleException` |
| Cancelar matrícula deletada (PATCH) | `DropEnrollmentUseCase` | Lança `ResourceNotFoundException` (invisível) |
| Soft delete de matrícula (DELETE — correção de erro) | `DeleteEnrollmentUseCase` | `deleted=True` — some do histórico |
| Soft delete de matrícula já deletada | `DeleteEnrollmentUseCase` | Lança `ResourceNotFoundException` |
| Listar matrículas ativas | `ListEnrollmentsUseCase` | Retorna apenas `status=active AND deleted=false` |
| Listar todas (sem filtro de status) | `ListEnrollmentsUseCase` | Retorna todos com `deleted=false` |
| Listar com `include_deleted=True` | `ListEnrollmentsUseCase` | Retorna todos, inclusive deletados |
| Mudança de role ALUNO→PROFESSOR | `UpdateTenantMemberRoleUseCase` | Matrículas ativas (não deletadas) → `dropped` |
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
| Cancelar matrícula por evento legítimo (ADMIN) | `PATCH .../enrollments/{id}` | `204` |
| Matricular aluno que havia sido cancelado (PATCH) → deve reativar | `POST .../enrollments` | `201` (reativado) |
| Remover matrícula por erro administrativo (ADMIN) | `DELETE .../enrollments/{id}` | `204` |
| Matricular aluno após soft delete → deve criar novo registro | `POST .../enrollments` | `201` (novo) |
| PATCH/DELETE por PROFESSOR deve falhar | `PATCH ou DELETE .../enrollments/{id}` | `403` |
| Aluno aparece em listagem após matrícula | `GET .../enrollments` | `200` (contém o aluno) |
| Aluno com `status=dropped` NÃO aparece em `?status=active` | `GET .../enrollments?status=active` | `200` (sem o aluno) |
| Aluno com `status=dropped` APARECE sem filtro de status | `GET .../enrollments` | `200` (presente com dropped) |
| Aluno deletado NÃO aparece em nenhuma listagem normal | `GET .../enrollments` | `200` (ausente) |
| Aluno deletado APARECE com `include_deleted=true` (ADMIN) | `GET .../enrollments?include_deleted=true` | `200` (presente) |
| Mudança de role → matrículas ficam `dropped` (não deletadas) | `PATCH .../members/role` + `GET .../enrollments` | `200` (status=dropped, visível no histórico) |

---

## Checklist de implementação

- [ ] Enum `EnrollmentStatus` criado em `src/shared/enums/enrollment_status.py`
- [ ] Model `EnrollmentModel` criado em `src/infra/database/models/enrollment.py` (com `deleted` + `status`, sem `UniqueConstraint`)
- [ ] `EnrollmentModel` registrado em `src/infra/database/models/__init__.py`
- [ ] Migration gerada — **verificar manualmente** se o `CREATE UNIQUE INDEX ... WHERE deleted = false` foi incluído (Alembic pode não detectar `postgresql_where` via autogenerate)
- [ ] Migration aplicada (`uv run alembic upgrade head`)
- [ ] Entidade `Enrollment` criada em `src/modules/enrollment/domain/entities/enrollment.py`
- [ ] Protocol `EnrollmentRepository` criado (com `include_deleted` em todos os métodos de busca e `drop_all_active_for_member`)
- [ ] Mapper `EnrollmentMapper` criado (mapeando campo `deleted`)
- [ ] `EnrollmentSQLAlchemyRepository` criado (filtros de `deleted` em todas as queries e `UPDATE ... WHERE` em batch)
- [ ] `EnrollStudentUseCase` implementado (reativação de `dropped`, respeita `deleted`)
- [ ] `ListEnrollmentsUseCase` implementado (com `include_deleted` e filtro de `status`)
- [ ] `DropEnrollmentUseCase` implementado (PATCH — muda `status=dropped`, preserva histórico)
- [ ] `DeleteEnrollmentUseCase` implementado (DELETE — muda `deleted=True`, correção de erro, ADMIN only)
- [ ] `UpdateTenantMemberRoleUseCase` modificado para chamar `drop_all_active_for_member`
- [ ] Schemas Pydantic criados
- [ ] Router criado com 4 rotas e registrado em `main.py`
- [ ] Testes unitários escritos e passando (cenários de `dropped` vs `deleted` distintos)
- [ ] Testes E2E escritos e passando (incluindo cenário de rematrícula após soft delete)
- [ ] `uv run pytest` — todos os testes passando sem erros

---

## Melhorias Pós-Plano

Funcionalidades a serem implementadas após a conclusão do plano principal acima.

---

### 🟡 Recomendado — `GET /{enrollment_id}` e `GET /members/{id}/enrollments`

#### `GET /enrollments/{enrollment_id}` — buscar matrícula individual

Padrão REST básico: qualquer recurso que pode ser criado deve poder ser consultado individualmente. Útil para o front validar o estado de uma matrícula específica.

**Use case:** `GetEnrollmentUseCase`

```python
@router.get("/{enrollment_id}", response_model=EnrollmentResponse)
async def get_enrollment(tenant_id, subject_class_id, enrollment_id, ...):
    """Retorna uma matrícula específica pelo ID."""
```

**Repositório** — adicionar método:
```python
async def find_by_id(self, enrollment_id: UUID, include_deleted: bool = False) -> Enrollment | None: ...
# (já existente no protocolo — apenas garantir que o router expõe via GET)
```

---

#### `GET /tenants/{tenant_id}/members/{member_id}/enrollments` — turmas do aluno

O inverso da listagem atual: "alunos de uma turma" → "turmas em que um aluno está matriculado". Essencial para exibir o **horário do aluno** e é exposto por todos os LMS de mercado (Canvas, Moodle, Google Classroom).

**Use case:** `ListEnrollmentsByMemberUseCase`

```python
@router.get(
    "/tenants/{tenant_id}/members/{member_id}/enrollments",
    response_model=list[EnrollmentResponse],
    tags=["enrollments"],
)
async def list_enrollments_by_member(tenant_id, member_id, status=None, ...):
    """Lista todas as turmas em que um aluno está matriculado."""
```

**Repositório** — adicionar método:
```python
async def list_by_member(
    self,
    tenant_member_id: UUID,
    status: EnrollmentStatus | None = None,
    include_deleted: bool = False,
) -> list[Enrollment]: ...
```

**SQL:**
```sql
SELECT * FROM subject_class_enrollments
WHERE tenant_member_id = :id
  AND deleted = false
  AND (:status IS NULL OR status = :status);
```

**Índice adicional necessário** (já existe): `idx_enrollments_tenant_member_id`.

---

### 🟡 Recomendado — Campos de auditoria temporal (`dropped_at`, `deleted_at`)

Registrar **quando** cada evento ocorreu permite relatórios de desistência por período, auditoria administrativa e rastreabilidade.

**Alterações no model:**
```python
dropped_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True, default=None
)
deleted_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True, default=None
)
```

**Regras de preenchimento:**

| Campo | Quando é preenchido | Quem preenche |
|---|---|---|
| `dropped_at` | Ao executar `DropEnrollmentUseCase` ou `drop_all_active_for_member` | Use case / repositório |
| `deleted_at` | Ao executar `DeleteEnrollmentUseCase` | Use case |

**Migration adicional:**
```sql
ALTER TABLE subject_class_enrollments
  ADD COLUMN dropped_at TIMESTAMPTZ DEFAULT NULL,
  ADD COLUMN deleted_at TIMESTAMPTZ DEFAULT NULL;
```

**Impacto no `drop_all_active_for_member`:**
```python
.values(
    status=EnrollmentStatus.DROPPED,
    dropped_at=datetime.now(timezone.utc),  # ← adicionar
)
```

**Schema de resposta** — expor os campos opcionalmente:
```python
class EnrollmentResponse(BaseModel):
    ...
    dropped_at: datetime | None = None
    deleted_at: datetime | None = None
```

---

### 🟢 Opcional — `drop_reason` (rastreio de causa do cancelamento)

Distinguir cancelamentos manuais (admin) de automáticos (mudança de role) sem precisar analisar logs.

**Enum:**
```python
# src/shared/enums/drop_reason.py
from enum import Enum

class DropReason(str, Enum):
    ADMIN_CANCELLATION = "admin_cancellation"  # ADMIN cancelou manualmente via PATCH
    ROLE_CHANGE = "role_change"                # Cancelamento automático por mudança de role
```

**Alteração no model:**
```python
from sqlalchemy import Enum as SAEnum
from shared.enums.drop_reason import DropReason

drop_reason: Mapped[DropReason | None] = mapped_column(
    SAEnum(DropReason, name="drop_reason", create_type=True),
    nullable=True,
    default=None,
)
```

**Preenchimento:**

| Operação | `drop_reason` |
|---|---|
| `DropEnrollmentUseCase` (PATCH manual) | `DropReason.ADMIN_CANCELLATION` |
| `drop_all_active_for_member` (role change) | `DropReason.ROLE_CHANGE` |
| `DeleteEnrollmentUseCase` (soft delete) | `None` (não aplicável — não é um cancelamento) |

**Migration adicional:**
```sql
CREATE TYPE drop_reason AS ENUM ('admin_cancellation', 'role_change');

ALTER TABLE subject_class_enrollments
  ADD COLUMN drop_reason drop_reason DEFAULT NULL;
```
