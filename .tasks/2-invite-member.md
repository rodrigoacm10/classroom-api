# Task 2 — Sistema de Invites por E-mail para Tenants

> **Objetivo**: Implementar o fluxo completo de convites por e-mail para membros de uma
> Tenant/Instituição. Um ADMIN envia um convite para um e-mail; o convidado recebe um
> link com token único, clica, autentica (ou cria conta) e aceita o convite,
> sendo vinculado automaticamente como `TenantMember` com a role definida pelo ADMIN.
>
> **Entrega esperada**: `POST /tenants/{tenant_id}/invites`,
> `GET /invites/{token}`, `POST /invites/{token}/accept`.

---

## Conceito central — fluxo do invite em duas etapas

```
ADMIN (logado na tenant)
  │
  └─► POST /tenants/{id}/invites  { email, role }
        │
        ├─ Gera token único (secrets.token_urlsafe(32))
        ├─ Salva TenantInvite no banco  (status: pendente)
        └─ Dispara e-mail via Resend
              │
              └─► Link: {FRONTEND_URL}/invites/accept?token=abc123
                    │
                    ├─ Usuário JÁ tem conta → faz login → POST /invites/{token}/accept
                    └─ Usuário SEM conta    → cria conta → POST /invites/{token}/accept
                          │
                          └─ Cria TenantMember(tenant_id, user_id, role)
                          └─ Marca invite.accepted_at = now()
```

---

## Visão geral da ordem de implementação

```
infra/database/models/tenant_invite.py   ← 1. Model SQLAlchemy TenantInviteModel
        │
alembic/versions/XXX_create_tenant_invites_table.py  ← 2. Migration
        │
infra/email/resend_client.py             ← 3. Cliente Resend (infra de e-mail)
infra/email/templates/invite.html        ← 4. Template HTML do e-mail
        │
modules/tenant/
  domain/entities/tenant_invite.py       ← 5. Entidade de domínio TenantInvite
  domain/repositories/tenant_invite_repository.py ← 6. Protocol (interface)
  infra/mappers/tenant_invite_mapper.py  ← 7. Mapper Model ↔ Entity
  infra/repositories/tenant_invite_sqlalchemy_repository.py ← 8. Implementação
  application/use_cases/send_invite.py   ← 9. SendInviteUseCase
  application/use_cases/get_invite.py    ← 10. GetInviteUseCase
  application/use_cases/accept_invite.py ← 11. AcceptInviteUseCase
  interface/schemas/tenant_schemas.py    ← 12. Novos schemas de request/response
  interface/router.py                    ← 13. 3 novas rotas HTTP
        │
config/settings.py                       ← 14. Variáveis de e-mail
tests/                                   ← 15. Testes unitários e E2E
```

---

## Passo 1 — Model SQLAlchemy `TenantInviteModel`

```python
# src/infra/database/models/tenant_invite.py
import secrets
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infra.database.base import Base
from shared.enums.user_role import UserRole


class TenantInviteModel(Base):
    __tablename__ = "tenant_invites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False
    )
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

> **Notas de design:**
> - `invited_by` usa `ondelete="SET NULL"` para preservar o histórico de invites mesmo que o usuário que convidou seja removido.
> - `token` é gerado com `secrets.token_urlsafe(32)` → 256 bits de entropia, URL-safe.
> - `expires_at` é calculado no use case (agora + `settings.invite_expire_hours`).

---

## Passo 2 — Migration Alembic

Gerado automaticamente após a criação do model:

```bash
uv run alembic revision --autogenerate -m "create tenant_invites table"
uv run alembic upgrade head
```

A migration criará:
```sql
CREATE TABLE tenant_invites (
    id          UUID PRIMARY KEY,
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    invited_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    email       VARCHAR(255) NOT NULL,
    role        user_role NOT NULL,
    token       VARCHAR(64) UNIQUE NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ix_tenant_invites_token ON tenant_invites(token);
CREATE INDEX ix_tenant_invites_email ON tenant_invites(email);
```

---

## Passo 3 — Cliente Resend

```python
# src/infra/email/resend_client.py
import resend

from config.settings import settings


def _get_client() -> resend.Resend:
    return resend.Resend(api_key=settings.resend_api_key)


async def send_invite_email(
    to_email: str,
    tenant_name: str,
    inviter_name: str,
    role: str,
    invite_link: str,
    expires_in_hours: int,
) -> None:
    """Envia o e-mail de convite para participar de uma instituição."""
    client = _get_client()

    html = _render_invite_template(
        tenant_name=tenant_name,
        inviter_name=inviter_name,
        role=role,
        invite_link=invite_link,
        expires_in_hours=expires_in_hours,
    )

    client.emails.send({
        "from": settings.email_from,
        "to": [to_email],
        "subject": f"Você foi convidado para participar de {tenant_name}",
        "html": html,
    })


def _render_invite_template(...) -> str:
    # Carrega e renderiza o template HTML (ver Passo 4)
    ...
```

> **Nota**: A função de envio é mantida síncrona intencionalmente para simplicidade inicial.
> Se necessário, pode ser migrada para uma task Celery no futuro.

---

## Passo 4 — Template HTML do E-mail

```
# src/infra/email/templates/invite.html
```

Um template HTML responsivo contendo:
- Nome da instituição
- Nome de quem convidou
- Role que será atribuída (em português: "Administrador", "Professor", "Aluno", "Coordenador")
- Botão de aceite com o link
- Validade do convite (ex: "Este convite expira em 72 horas")
- Mensagem caso não reconheça o convite

---

## Passo 5 — Entidade de Domínio `TenantInvite`

```python
# src/modules/tenant/domain/entities/tenant_invite.py
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from shared.enums.user_role import UserRole


@dataclass
class TenantInvite:
    tenant_id: UUID
    email: str
    role: UserRole
    expires_at: datetime
    invited_by: UUID | None = None
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    accepted_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_accepted(self) -> bool:
        return self.accepted_at is not None

    @property
    def is_pending(self) -> bool:
        return not self.is_accepted and not self.is_expired
```

---

## Passo 6 — Interface do Repositório (Protocol)

```python
# src/modules/tenant/domain/repositories/tenant_invite_repository.py
from typing import Protocol
from uuid import UUID

from modules.tenant.domain.entities.tenant_invite import TenantInvite


class TenantInviteRepository(Protocol):

    async def find_by_token(self, token: str) -> TenantInvite | None: ...

    async def find_by_email_and_tenant(
        self, email: str, tenant_id: UUID
    ) -> TenantInvite | None: ...

    async def save(self, invite: TenantInvite) -> TenantInvite: ...
```

---

## Passo 7 — Mapper

```python
# src/modules/tenant/infra/mappers/tenant_invite_mapper.py
from infra.database.models.tenant_invite import TenantInviteModel
from modules.tenant.domain.entities.tenant_invite import TenantInvite


class TenantInviteMapper:

    @staticmethod
    def to_domain(model: TenantInviteModel) -> TenantInvite:
        return TenantInvite(
            id=model.id,
            tenant_id=model.tenant_id,
            invited_by=model.invited_by,
            email=model.email,
            role=model.role,
            token=model.token,
            expires_at=model.expires_at,
            accepted_at=model.accepted_at,
            created_at=model.created_at,
        )

    @staticmethod
    def to_model(entity: TenantInvite) -> TenantInviteModel:
        return TenantInviteModel(
            id=entity.id,
            tenant_id=entity.tenant_id,
            invited_by=entity.invited_by,
            email=entity.email,
            role=entity.role,
            token=entity.token,
            expires_at=entity.expires_at,
            accepted_at=entity.accepted_at,
        )
```

---

## Passo 8 — Repositório SQLAlchemy

```python
# src/modules/tenant/infra/repositories/tenant_invite_sqlalchemy_repository.py
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.tenant_invite import TenantInviteModel
from modules.tenant.domain.entities.tenant_invite import TenantInvite
from modules.tenant.infra.mappers.tenant_invite_mapper import TenantInviteMapper


class TenantInviteSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_token(self, token: str) -> TenantInvite | None:
        stmt = select(TenantInviteModel).where(TenantInviteModel.token == token)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return TenantInviteMapper.to_domain(model) if model else None

    async def find_by_email_and_tenant(
        self, email: str, tenant_id: UUID
    ) -> TenantInvite | None:
        stmt = select(TenantInviteModel).where(
            TenantInviteModel.email == email,
            TenantInviteModel.tenant_id == tenant_id,
            TenantInviteModel.accepted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return TenantInviteMapper.to_domain(model) if model else None

    async def save(self, invite: TenantInvite) -> TenantInvite:
        model = TenantInviteMapper.to_model(invite)
        merged = await self.session.merge(model)
        await self.session.commit()
        await self.session.refresh(merged)
        return TenantInviteMapper.to_domain(merged)
```

---

## Passo 9 — `SendInviteUseCase`

```python
# src/modules/tenant/application/use_cases/send_invite.py
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from infra.email.resend_client import send_invite_email
from modules.tenant.domain.entities.tenant_invite import TenantInvite
from modules.tenant.domain.repositories.tenant_invite_repository import TenantInviteRepository
from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository, TenantRepository
from modules.user.domain.entities.user import User
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class SendInviteInput:
    tenant_id: UUID
    email: str
    role: UserRole
    invited_by: User


class SendInviteUseCase:

    def __init__(
        self,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
        invite_repo: TenantInviteRepository,
        expire_hours: int = 72,
        frontend_url: str = "http://localhost:3000",
    ) -> None:
        ...

    async def execute(self, data: SendInviteInput) -> TenantInvite:
        # 1. Verifica se a tenant existe e não está deletada
        # 2. Verifica se o convidado já é membro da tenant
        # 3. Verifica se já existe um invite pendente para esse e-mail/tenant
        # 4. Cria o TenantInvite com expiração
        # 5. Persiste o invite
        # 6. Monta o link: {frontend_url}/invites/accept?token={invite.token}
        # 7. Dispara o e-mail via Resend
        # 8. Retorna o invite salvo
        ...
```

**Regras de negócio validadas:**
- Tenant existe e não está deletada → `ResourceNotFoundException`
- O convidado já é membro da tenant → `BusinessRuleException("Usuário já é membro desta instituição.")`
- Já existe um invite pendente (não aceito e não expirado) para o mesmo e-mail + tenant → `BusinessRuleException("Já existe um convite pendente para este e-mail.")`

---

## Passo 10 — `GetInviteUseCase`

```python
# src/modules/tenant/application/use_cases/get_invite.py
```

Responsável por retornar os detalhes de um invite pelo token, para o frontend exibir a tela de aceite.

**Retorna:**
- Nome da tenant
- E-mail convidado
- Role oferecida
- Status: `pending` | `accepted` | `expired`

---

## Passo 11 — `AcceptInviteUseCase`

```python
# src/modules/tenant/application/use_cases/accept_invite.py
```

**Fluxo:**
1. Busca o invite pelo token → `ResourceNotFoundException` se não encontrado
2. Valida se o invite já foi aceito → `BusinessRuleException`
3. Valida se o invite expirou → `BusinessRuleException`
4. Valida se o e-mail do usuário logado bate com o e-mail do invite → `ForbiddenException`
5. Verifica se o usuário já é membro (caso raro de race condition)
6. Cria o `TenantMember`
7. Marca `invite.accepted_at = datetime.now(timezone.utc)`
8. Persiste ambos

---

## Passo 12 — Schemas Pydantic

```python
# Adicionar em: src/modules/tenant/interface/schemas/tenant_schemas.py

class SendInviteRequest(BaseModel):
    email: EmailStr
    role: UserRole

class InviteStatusResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    tenant_name: str
    email: str
    role: UserRole
    status: Literal["pending", "accepted", "expired"]
    expires_at: datetime
    created_at: datetime
    model_config = {"from_attributes": True}
```

---

## Passo 13 — Novas Rotas HTTP

```python
# Adicionar em: src/modules/tenant/interface/router.py

# Enviar convite (somente ADMIN da tenant ativa)
POST /tenants/{tenant_id}/invites
  - Body: { email, role }
  - Auth: JWT com tenant_id + role ADMIN
  - Resposta 201: InviteStatusResponse

# Consultar detalhes de um invite (público — sem autenticação)
GET /invites/{token}
  - Resposta 200: InviteStatusResponse (com tenant_name, role, status)
  - Resposta 404: convite não encontrado

# Aceitar um invite (requer autenticação — o usuário precisa estar logado)
POST /invites/{token}/accept
  - Auth: JWT do usuário (base, sem tenant_id obrigatório)
  - Resposta 200: TenantMemberResponse
  - Resposta 400: invite expirado ou já aceito
  - Resposta 403: e-mail do usuário ≠ e-mail do convite
```

---

## Passo 14 — Atualizar `config/settings.py`

```python
# Variáveis novas a adicionar:
resend_api_key: str = ""
email_from: str = "noreply@seudominio.com"
frontend_url: str = "http://localhost:3000"
invite_expire_hours: int = 72
```

E adicionar ao `.env`:
```
RESEND_API_KEY=re_xxxxxxxxxxxx
EMAIL_FROM=noreply@classroom.app
FRONTEND_URL=http://localhost:3000
INVITE_EXPIRE_HOURS=72
```

---

## Passo 15 — Instalar dependência

```bash
uv add resend
```

---

## Passo 16 — Testes

### Testes Unitários (`tests/unit/modules/tenant/`)

Criar `tests/unit/fakes/fake_tenant_invite_repository.py` com implementação in-memory.

**Casos a cobrir em `test_invite_use_cases.py`:**

```
SendInviteUseCase:
  - [ ] Sucesso: invite criado com status pendente
  - [ ] Erro: tenant não encontrada ou deletada
  - [ ] Erro: usuário já é membro da tenant
  - [ ] Erro: já existe invite pendente para o mesmo e-mail + tenant

GetInviteUseCase:
  - [ ] Sucesso: retorna invite com status "pending"
  - [ ] Sucesso: retorna invite com status "accepted"
  - [ ] Sucesso: retorna invite com status "expired"
  - [ ] Erro: token não encontrado

AcceptInviteUseCase:
  - [ ] Sucesso: cria TenantMember e marca accepted_at
  - [ ] Erro: token não encontrado
  - [ ] Erro: invite já aceito
  - [ ] Erro: invite expirado
  - [ ] Erro: e-mail do usuário ≠ e-mail do invite
```

### Testes E2E (`tests/e2e/modules/tenant/test_invite_router.py`)

```
  - [ ] POST /tenants/{id}/invites → 201 com invite pendente
  - [ ] POST /tenants/{id}/invites sem autenticação → 401
  - [ ] POST /tenants/{id}/invites com role não-ADMIN → 403
  - [ ] POST /tenants/{id}/invites para membro já existente → 409
  - [ ] GET /invites/{token} → 200 com detalhes do invite
  - [ ] GET /invites/{token} inválido → 404
  - [ ] POST /invites/{token}/accept → 200 cria membro
  - [ ] POST /invites/{token}/accept com e-mail diferente → 403
  - [ ] POST /invites/{token}/accept expirado → 400
  - [ ] POST /invites/{token}/accept já aceito → 400
```

> **Nota sobre testes de e-mail**: nos testes, o cliente Resend deve ser mockado
> para não realizar chamadas reais. Usar `unittest.mock.patch` ou injeção de dependência.

---

## Checklist de implementação

- [ ] Instalar dependência `resend` via `uv add resend`
- [ ] Criar `TenantInviteModel` em `infra/database/models/`
- [ ] Registrar o model em `infra/database/models/__init__.py`
- [ ] Gerar e aplicar migration Alembic
- [ ] Criar `infra/email/resend_client.py`
- [ ] Criar template HTML do e-mail
- [ ] Criar entidade `TenantInvite` em `domain/entities/`
- [ ] Criar Protocol `TenantInviteRepository` em `domain/repositories/`
- [ ] Criar `TenantInviteMapper`
- [ ] Criar `TenantInviteSQLAlchemyRepository`
- [ ] Criar `SendInviteUseCase`
- [ ] Criar `GetInviteUseCase`
- [ ] Criar `AcceptInviteUseCase`
- [ ] Atualizar schemas Pydantic
- [ ] Adicionar 3 novas rotas no router de tenants
- [ ] Atualizar `settings.py` com variáveis de e-mail
- [ ] Atualizar `.env.example` (se existir)
- [ ] Criar `FakeTenantInviteRepository` para testes
- [ ] Escrever testes unitários
- [ ] Escrever testes E2E (com mock do Resend)
- [ ] Executar suite completa de testes (`uv run pytest`)

---

## Decisões de design

| Decisão | Justificativa |
|---|---|
| Token via `secrets.token_urlsafe(32)` | 256 bits de entropia, URL-safe, sem colisões práticas |
| E-mail não muda o role se já for membro | Evita escalonamento não-intencional de privilégios |
| Aceite requer autenticação prévia | Garante que só o dono do e-mail aceite o convite |
| `GET /invites/{token}` é público | Permite o frontend exibir a tela de aceite antes do login |
| `ondelete="SET NULL"` no `invited_by` | Histórico de invites preservado mesmo após remoção do usuário |
| Apenas 1 invite pendente por e-mail + tenant | Evita spam de e-mails e confusão no estado |
