# Task 9 — Application Event Bus para Notificações Desacopladas

> **Objetivo**: Refatorar o sistema de despacho de notificações push para utilizar o padrão
> **Application Event Bus**, desacoplando completamente os Use Cases da infraestrutura de
> notificações (Celery, FCM, EnrollmentRepository). Cada Use Case passa a publicar um evento
> de domínio que descreve *o que aconteceu*, e handlers de notificação na camada de infraestrutura
> são responsáveis por reagir a esses eventos.
>
> **Entrega esperada desta etapa**:
>
> - `AttendanceSessionOpenedEvent` — dispara push de "chamada aberta" para alunos
> - `AttendanceSessionClosedEvent` — dispara push de "chamada encerrada" para alunos
> - `EventDispatcher` in-memory — barramento central de eventos da aplicação
> - Task Celery genérica `send_push_notification` (substitui a task específica `send_attendance_opened_notification`)
> - `OpenAttendanceSessionUseCase` e `CloseAttendanceSessionUseCase` refatorados para publicar eventos

> [!WARNING]
> **Pré-requisito**: Esta etapa depende da [Task 8 — FCM Push Notifications](./8-fcm-push-notifications.md).
> A infraestrutura do Celery, Firebase Admin SDK e tokens FCM já existem e **não serão alterados**.

> [!NOTE]
> **Fora do escopo desta etapa:**
>
> - 🔔 **Notificações de outros módulos** (matrícula aprovada, turma criada) — implementadas em etapas futuras.
> - 📊 **Rastreamento de entrega** (`delivery_status`, `opened_at`) — requer webhook do FCM.
> - 🔁 **Dead Letter Queue (DLQ)** — implementado em etapa futura.
> - 🗄️ **Transactional Outbox Pattern** — para garantia de entrega em caso de queda do Redis, fora do escopo atual.

---

## Motivação — Por que Refatorar?

### Estado Atual (Acoplado)

O `OpenAttendanceSessionUseCase` hoje possui responsabilidades mistas:

```
OpenAttendanceSessionUseCase
  ├── Regra de negócio: valida tenant, sala, permissão
  ├── Regra de negócio: gera day_code e salva sessão
  ├── Infraestrutura: injeta EnrollmentRepository para buscar tokens FCM
  ├── Infraestrutura: importa e chama send_attendance_opened_notification.delay()
  ├── Infraestrutura: trata exceção com try/except
  └── Infraestrutura: grava log com logger.exception()
```

Consequência: qualquer novo tipo de notificação (fechamento de chamada, matrícula, etc.)
requer **modificar o Use Case**, injetando mais dependências e adicionando mais `try/except`.

### Estado Desejado (Desacoplado)

```
OpenAttendanceSessionUseCase
  ├── Regra de negócio: valida tenant, sala, permissão
  ├── Regra de negócio: gera day_code e salva sessão
  └── Publica evento: AttendanceSessionOpenedEvent(session_id, subject_class_id, ...)

          ↓  [EventDispatcher — barramento in-memory]

AttendancePushNotificationHandler
  ├── Escuta AttendanceSessionOpenedEvent
  ├── Busca tokens FCM dos alunos (EnrollmentRepository)
  └── Chama send_push_notification.delay(title, body, data, tokens)
```

A partir desse ponto, adicionar um novo efeito colateral (ex: log de auditoria, e-mail para o coordenador)
é apenas criar um novo Handler e registrá-lo no `EventDispatcher`. **Nenhum Use Case é modificado**.

---

## Conceito Central — Application Event Bus

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         USE CASE (Application Layer)                      │
│                                                                            │
│   use_case.execute(data)                                                   │
│       └── saved = session_repo.save(session)                              │
│       └── dispatcher.publish(AttendanceSessionOpenedEvent(...))   ◄──── │
└──────────────────────────────────────────────────────────────────┼───────┘
                                                                    │ (sincrono in-memory)
                         ┌──────────────────────────────────────────┘
                         ▼
              [EventDispatcher.publish(event)]
                         │
         ┌───────────────┴────────────────────┐
         ▼                                    ▼
AttendancePushNotificationHandler      AuditLogHandler (futuro)
   (infra/handlers/notification.py)
         │
         ├── enrollment_repo.find_active_fcm_tokens()
         └── send_push_notification.delay(title, body, data, tokens)
                         │
                    [Redis / Celery]
                         │
                   [Worker Celery]
                         │
                    [Firebase FCM]
                         │
              [Dispositivos dos Alunos]
```

> **Por que "Application Event" e não "Domain Event"?**
>
> Em DDD puro, um **Domain Event** é emitido pela própria entidade de domínio (`AttendanceSession`)
> e coletado pelo repositório após o `save()`. Um **Application Event** é emitido pelo Use Case
> diretamente após coordenar a operação de domínio.
>
> Para o escopo atual do projeto, o **Application Event** é a escolha correta pois:
> 1. As entidades ainda não implementam auto-emissão de eventos (aumentaria a complexidade das entidades).
> 2. O EventDispatcher não precisa de integração com o ORM/repositório.
> 3. O comportamento é idêntico para o caso de uso prático.

---

## Arquitetura do Módulo

```
src/
├── shared/
│   └── events/
│       ├── __init__.py
│       ├── base_event.py                          ← [NEW] BaseEvent (dataclass abstrata)
│       └── event_dispatcher.py                    ← [NEW] EventDispatcher (barramento in-memory)
│
├── modules/
│   └── attendance/
│       ├── domain/
│       │   └── events/
│       │       ├── __init__.py
│       │       └── attendance_events.py           ← [NEW] AttendanceSessionOpenedEvent, AttendanceSessionClosedEvent
│       │
│       ├── application/
│       │   └── handlers/
│       │       ├── __init__.py
│       │       └── attendance_notification_handler.py  ← [NEW] Handler de push notification
│       │
│       └── application/use_cases/
│           ├── open_session.py                    ← [MODIFY] Remove import Celery/EnrollmentRepo, publica evento
│           └── close_session.py                   ← [MODIFY] Publica AttendanceSessionClosedEvent
│
└── infra/
    └── tasks/
        ├── celery_app.py                          ← (sem alteração)
        └── notification_tasks.py                  ← [MODIFY] Task genérica send_push_notification

src/main.py                                        ← [MODIFY] Inicializa e registra handlers no EventDispatcher

tests/
├── unit/modules/attendance/
│   ├── test_open_session_use_case.py              ← [MODIFY] Testa publicação do evento
│   └── test_close_session_use_case.py             ← [MODIFY] Testa publicação do evento
└── unit/shared/
    └── test_event_dispatcher.py                   ← [NEW] Testa o roteamento de eventos
```

---

## Parte 1 — Evento Base e EventDispatcher

### 1.1 `shared/events/base_event.py`

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass(frozen=True)
class BaseEvent:
    """Classe base para todos os Application Events do sistema."""
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

### 1.2 `shared/events/event_dispatcher.py`

```python
import logging
from collections import defaultdict
from typing import Callable, Awaitable, Type

from shared.events.base_event import BaseEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[BaseEvent], Awaitable[None]]


class EventDispatcher:
    """
    Barramento de eventos in-memory da aplicação.

    Uso:
      dispatcher = EventDispatcher()
      dispatcher.register(AttendanceSessionOpenedEvent, handler_func)
      await dispatcher.publish(AttendanceSessionOpenedEvent(...))
    """

    def __init__(self) -> None:
        self._handlers: dict[Type[BaseEvent], list[EventHandler]] = defaultdict(list)

    def register(self, event_type: Type[BaseEvent], handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: BaseEvent) -> None:
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Event handler %s failed for event %s (id=%s)",
                    handler.__name__,
                    type(event).__name__,
                    event.event_id,
                )
```

> **Por que o `try/except` está no `EventDispatcher` e não no Use Case?**
>
> O Use Case nunca deve saber que um handler falhou. O `try/except` é responsabilidade do barramento:
> ele garante que, se um handler falhar, os outros handlers do mesmo evento continuam sendo executados
> (comportamento **fire-and-continue**). O Use Case apenas publica o evento e esquece.

---

## Parte 2 — Eventos de Domínio da Chamada

### `modules/attendance/domain/events/attendance_events.py`

```python
from dataclasses import dataclass
from uuid import UUID

from shared.events.base_event import BaseEvent


@dataclass(frozen=True)
class AttendanceSessionOpenedEvent(BaseEvent):
    """
    Publicado quando um professor abre uma sessão de chamada.
    Consumido por: AttendancePushNotificationHandler (envia push para alunos).
    """
    session_id: UUID
    subject_class_id: UUID
    subject_class_name: str
    day_code: str
    duration_minutes: int


@dataclass(frozen=True)
class AttendanceSessionClosedEvent(BaseEvent):
    """
    Publicado quando a chamada é encerrada (manual ou expiração).
    Consumido por: AttendancePushNotificationHandler (envia push para alunos).
    """
    session_id: UUID
    subject_class_id: UUID
    subject_class_name: str
```

---

## Parte 3 — Task Celery Genérica

### `infra/tasks/notification_tasks.py` — [MODIFY]

A task específica `send_attendance_opened_notification` é **substituída** por uma task genérica
`send_push_notification` que recebe `title`, `body` e `data` como parâmetros:

```python
@celery_app.task(
    name="notification.send_push_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(FirebaseError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def send_push_notification(
    self: Task,
    title: str,
    body: str,
    data: dict[str, str],
    fcm_tokens: list[str],
) -> dict[str, int]:
    """
    Task genérica de envio de push notification via Firebase Cloud Messaging.
    Suporta qualquer tipo de notificação (abertura de chamada, fechamento, matrícula, etc.).
    """
    ...
```

---

## Parte 4 — Handler de Notificação

### `modules/attendance/application/handlers/attendance_notification_handler.py`

```python
import logging

from modules.attendance.domain.events.attendance_events import (
    AttendanceSessionClosedEvent,
    AttendanceSessionOpenedEvent,
)
from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository

logger = logging.getLogger(__name__)


class AttendancePushNotificationHandler:
    """
    Escuta eventos de chamada e despacha notificações push para os alunos da turma.
    Cada método corresponde a um tipo de evento.
    """

    def __init__(self, enrollment_repo: EnrollmentRepository) -> None:
        self.enrollment_repo = enrollment_repo

    async def on_session_opened(self, event: AttendanceSessionOpenedEvent) -> None:
        from infra.tasks.notification_tasks import send_push_notification
        tokens = await self.enrollment_repo.find_active_fcm_tokens(event.subject_class_id)
        if tokens:
            send_push_notification.delay(
                title=f"📋 Chamada Aberta — {event.subject_class_name}",
                body=(
                    f"O professor iniciou a chamada! Você tem {event.duration_minutes} "
                    f"minutos. Código: {event.day_code}"
                ),
                data={
                    "type": "ATTENDANCE_OPENED",
                    "day_code": event.day_code,
                    "subject_class_name": event.subject_class_name,
                    "duration_minutes": str(event.duration_minutes),
                },
                fcm_tokens=tokens,
            )

    async def on_session_closed(self, event: AttendanceSessionClosedEvent) -> None:
        from infra.tasks.notification_tasks import send_push_notification
        tokens = await self.enrollment_repo.find_active_fcm_tokens(event.subject_class_id)
        if tokens:
            send_push_notification.delay(
                title=f"🔒 Chamada Encerrada — {event.subject_class_name}",
                body="A janela de confirmação de presença foi encerrada.",
                data={
                    "type": "ATTENDANCE_CLOSED",
                    "subject_class_name": event.subject_class_name,
                },
                fcm_tokens=tokens,
            )
```

---

## Parte 5 — Registro no `main.py`

O `EventDispatcher` é instanciado uma única vez (singleton da aplicação) e os handlers são
registrados no startup:

```python
# src/main.py
from shared.events.event_dispatcher import EventDispatcher
from modules.attendance.domain.events.attendance_events import (
    AttendanceSessionOpenedEvent,
    AttendanceSessionClosedEvent,
)

# Instância global do barramento (injetada nos Use Cases via DI)
event_dispatcher = EventDispatcher()

@app.on_event("startup")
async def register_event_handlers() -> None:
    # Handlers de notificação são instanciados aqui com suas dependências de infra
    from infra.database.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        from modules.enrollment.infra.repositories.enrollment_sqlalchemy_repository import (
            EnrollmentSQLAlchemyRepository,
        )
        from modules.attendance.application.handlers.attendance_notification_handler import (
            AttendancePushNotificationHandler,
        )
        handler = AttendancePushNotificationHandler(
            enrollment_repo=EnrollmentSQLAlchemyRepository(db)
        )
        event_dispatcher.register(AttendanceSessionOpenedEvent, handler.on_session_opened)
        event_dispatcher.register(AttendanceSessionClosedEvent, handler.on_session_closed)
```

> **Nota**: Os handlers de notificação recebem suas próprias sessões de banco independentes
> da sessão HTTP da requisição, pois são executados de forma assíncrona após o commit da transação principal.

---

## Parte 6 — Use Cases Refatorados

### `open_session.py` — [MODIFY]

```python
# Removido: import send_attendance_opened_notification
# Removido: import logging
# Removido: import EnrollmentRepository
# Adicionado: EventDispatcher

class OpenAttendanceSessionUseCase:

    def __init__(
        self,
        session_repo: AttendanceSessionRepository,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
        room_repo: RoomRepository,
        event_dispatcher: EventDispatcher,
    ) -> None:
        ...

    async def execute(self, data: OpenAttendanceSessionInput) -> AttendanceSession:
        # ... toda a lógica de negócio sem alteração ...

        saved_session = await self.session_repo.save(session)

        # Publicar evento — o Use Case não sabe quem vai reagir
        await self.event_dispatcher.publish(
            AttendanceSessionOpenedEvent(
                session_id=saved_session.id,
                subject_class_id=data.subject_class_id,
                subject_class_name=subject_class.name,
                day_code=saved_session.day_code,
                duration_minutes=data.duration_minutes,
            )
        )

        return saved_session
```

---

## Parte 7 — Validações de Negócio

Não existem novas validações de negócio nesta task — trata-se exclusivamente de uma
refatoração de arquitetura interna que não altera contratos de API.

---

## Parte 8 — Testes

### Estratégia

- **Testes unitários dos Use Cases**: verificar que o evento correto é publicado com os dados corretos.
  O `EventDispatcher` é substituído por um **spy** (fake que registra os eventos recebidos).
- **Testes unitários do EventDispatcher**: verificar roteamento correto e isolamento de falhas entre handlers.
- **Testes unitários dos Handlers**: verificar que o handler monta a mensagem correta e chama `send_push_notification.delay()` com os parâmetros corretos (mock do Celery).

### `test_event_dispatcher.py`

```python
async def test_dispatcher_routes_to_correct_handler():
    """Evento é entregue apenas ao handler registrado para aquele tipo."""

async def test_dispatcher_continues_after_handler_failure():
    """Se um handler falhar, o próximo handler do mesmo evento ainda é executado."""

async def test_dispatcher_ignores_unregistered_event():
    """Publicar evento sem handler registrado não lança exceção."""
```

### `test_open_session_use_case.py` — [MODIFY]

```python
async def test_open_session_publishes_opened_event():
    """Deve publicar AttendanceSessionOpenedEvent com os dados corretos após salvar sessão."""

async def test_open_session_event_contains_correct_day_code():
    """O evento publicado deve conter o day_code da sessão recém-criada."""
```

---

## Ordem de Implementação

```
1.  shared/events/base_event.py                              ← BaseEvent
2.  shared/events/event_dispatcher.py                       ← EventDispatcher com try/except por handler
3.  modules/attendance/domain/events/attendance_events.py   ← AttendanceSessionOpenedEvent + AttendanceSessionClosedEvent
4.  infra/tasks/notification_tasks.py                       ← Substituir task específica por send_push_notification genérica
5.  modules/attendance/application/handlers/               ← AttendancePushNotificationHandler
6.  modules/attendance/application/use_cases/open_session.py  ← Remover acoplamento, publicar evento
7.  modules/attendance/application/use_cases/close_session.py ← Publicar AttendanceSessionClosedEvent
8.  modules/attendance/interface/router.py                  ← Injetar EventDispatcher nos Use Cases
9.  src/main.py                                             ← Registrar handlers no startup
10. tests/unit/shared/test_event_dispatcher.py              ← Testes do barramento
11. tests/unit/modules/attendance/test_open_session_use_case.py   ← Adaptar testes existentes
12. tests/unit/modules/attendance/test_close_session_use_case.py  ← Adaptar testes existentes
```

---

## Checklist de Implementação

- [ ] Criar `shared/events/base_event.py`
- [ ] Criar `shared/events/event_dispatcher.py` com isolamento de falhas entre handlers
- [ ] Criar `modules/attendance/domain/events/attendance_events.py`
- [ ] Substituir `send_attendance_opened_notification` por `send_push_notification` genérica em `notification_tasks.py`
- [ ] Criar `AttendancePushNotificationHandler` com `on_session_opened` e `on_session_closed`
- [ ] Refatorar `OpenAttendanceSessionUseCase`: remover `EnrollmentRepository`, `logging`, import Celery; adicionar `EventDispatcher`
- [ ] Refatorar `CloseAttendanceSessionUseCase`: adicionar `EventDispatcher` e publicar `AttendanceSessionClosedEvent`
- [ ] Atualizar router de attendance para injetar `EventDispatcher` nos dois Use Cases
- [ ] Registrar handlers no startup do `main.py`
- [ ] Testes unitários do `EventDispatcher`
- [ ] Adaptar testes existentes de `open_session` e `close_session` para usar spy de eventos
- [ ] Testes unitários do `AttendancePushNotificationHandler`
