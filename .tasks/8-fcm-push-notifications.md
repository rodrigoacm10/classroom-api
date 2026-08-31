# Task 8 — Notificações Push via Firebase Cloud Messaging (FCM)

> **Objetivo**: Implementar o sistema de notificações push transacionais que dispara automaticamente
> para os alunos matriculados no momento em que o professor abre uma chamada de presença.
> A entrega das notificações deve ser **assíncrona** para não adicionar latência à resposta HTTP do professor.
>
> **Entrega esperada desta etapa**:
>
> - `POST /tenants/{tenant_id}/fcm-tokens` — aluno registra ou atualiza o token FCM do dispositivo
> - `DELETE /tenants/{tenant_id}/fcm-tokens/{device_id}` — aluno remove o token ao fazer logout
> - Disparo automático de notificação na abertura de chamada (`OpenAttendanceSessionUseCase`)

> [!WARNING]
> **Pré-requisito**: Esta etapa depende diretamente da [Task 6 — Módulo de Chamada](./6-attendance.md).
> O `OpenAttendanceSessionUseCase` já existe e será estendido nesta etapa para despachar a task Celery
> sem nenhuma modificação nas validações de negócio existentes.

> [!NOTE]
> **Fora do escopo desta etapa:**
>
> - 🔔 **Notificações de outros eventos** (ex: turma criada, matrícula aprovada, chamada encerrada) — implementadas em etapas futuras.
> - 📊 **Rastreamento de entrega** (`delivery_status`, `opened_at`) — requer webhook do FCM, adicionado em etapa futura.
> - 🔁 **Dead Letter Queue (DLQ)** — fila para mensagens que falharam após N tentativas, implementado em etapa futura.

---

## Conceito Central — Por que Assíncrono?

```
Fluxo SÍNCRONO (NÃO usar):
  Professor →  POST /open  →  FastAPI  →  FCM API (N alunos)  →  Response 201
                               ↑
                    Professor espera centenas de chamadas HTTP ao FCM
                    para só então receber a resposta. Inaceitável!

Fluxo ASSÍNCRONO (padrão de mercado):
  Professor →  POST /open  →  FastAPI  →  Celery .delay()  →  Response 201 (imediata)
                                              │
                                         [Fila Redis]
                                              │
                                         [Worker Celery] →  FCM API  →  Dispositivos dos Alunos
```

A resposta ao professor é retornada **imediatamente** após salvar a sessão no banco.
A notificação para os alunos é entregue em paralelo, pelo worker do Celery,
sem nenhum impacto na latência da API.

---

## Modelagem do Banco de Dados

### `user_fcm_tokens` — Tokens FCM dos Dispositivos

```
user_fcm_tokens
  ├── id              UUID (PK)                   DEFAULT gen_random_uuid()
  ├── user_id         FK → users.id               ON DELETE CASCADE
  ├── device_id       VARCHAR(64) NOT NULL        → UUID gerado pelo app (Keychain/Keystore)
  ├── fcm_token       TEXT NOT NULL               → Token emitido pelo SDK do Firebase
  ├── platform        VARCHAR(20) NOT NULL        → "android" | "ios"
  ├── app_version     VARCHAR(20) nullable        → versão do app para filtrar tokens antigos
  ├── updated_at      TIMESTAMPTZ DEFAULT now()
  └── UNIQUE(user_id, device_id)                 → um token por (usuário × dispositivo)
```

> **Por que `UNIQUE(user_id, device_id)` e não só em `fcm_token`?**
> O FCM Token pode ser rotacionado pelo SDK do Firebase a qualquer momento (ex: ao reinstalar o app,
> ao revogar credenciais, ao limpar dados do aplicativo). O identificador estável que **nunca muda**
> é o `device_id` — gerado pelo app na instalação e persistido no Keychain/Keystore do dispositivo.
> O upsert `ON CONFLICT (user_id, device_id) DO UPDATE SET fcm_token = ...` garante que
> o token mais recente do dispositivo seja sempre o armazenado.

### Ciclo de Vida dos Tokens e Limpeza Automática

1. **Login / Rotação de Token**: Ao fazer login ou quando o Firebase rotaciona o token, o app chama `POST /fcm-tokens`. Se for o mesmo `device_id`, o token antigo é substituído (Upsert).
2. **Logout**: Ao fazer logout, o app chama `DELETE /fcm-tokens/{device_id}` para remover o vinculo do dispositivo.
3. **Desinstalação ou Token Abandonado (`UNREGISTERED`)**: Se o aluno desinstalar o aplicativo, a resposta do Firebase ao tentar enviar o multicast indicará erro `UNREGISTERED` (ou `registration-token-not-registered`). O worker do Celery detecta esse código de erro específico e remove automaticamente a entrada inválida do banco de dados, mantendo a tabela sempre limpa.

### Query para Buscar Tokens dos Alunos de uma Turma

Não é uma tabela, mas a query usada pelo repositório para buscar tokens dos alunos de uma turma:

```sql
-- Busca fcm_tokens de todos os alunos com matrícula ACTIVE em uma turma
SELECT t.fcm_token
FROM enrollments e
JOIN tenant_members tm ON tm.id = e.tenant_member_id
JOIN users u ON u.id = tm.user_id
JOIN user_fcm_tokens t ON t.user_id = u.id
WHERE
    e.subject_class_id = :subject_class_id
    AND e.status = 'active'
    AND e.deleted = FALSE;
```

---

## Arquitetura do Módulo

```
src/
├── config/
│   └── settings.py                                    ← [MODIFY] Adicionar FIREBASE_CREDENTIALS_PATH e CELERY_*
│
├── infra/
│   ├── cache/
│   │   └── redis_client.py                            ← (já existe — sem alteração)
│   ├── firebase/
│   │   ├── __init__.py
│   │   └── client.py                                  ← [NEW] Inicialização singleton do Firebase Admin SDK
│   └── tasks/
│       ├── __init__.py
│       ├── celery_app.py                              ← [NEW] Instância do Celery configurada com Redis
│       └── notification_tasks.py                      ← [NEW] Task send_attendance_opened_notification
│
└── modules/
    ├── attendance/
    │   └── application/
    │       └── use_cases/
    │           └── open_session.py                    ← [MODIFY] Despacha a task após salvar a sessão
    └── notification/
        ├── domain/
        │   ├── entities/
        │   │   └── fcm_token.py                       ← [NEW] Entidade de domínio FCMToken
        │   └── repositories/
        │       └── fcm_token_repository.py            ← [NEW] Protocol do repositório de tokens
        ├── infra/
        │   ├── mappers/
        │   │   └── fcm_token_mapper.py                ← [NEW] Mapper Model ↔ Entity
        │   └── repositories/
        │       └── fcm_token_sqlalchemy_repository.py ← [NEW] Implementação SQLAlchemy (upsert)
        ├── application/
        │   └── use_cases/
        │       ├── register_fcm_token.py              ← [NEW] RegisterFCMTokenUseCase
        │       └── remove_fcm_token.py                ← [NEW] RemoveFCMTokenUseCase
        └── interface/
            ├── router.py                              ← [NEW] Endpoints /fcm-tokens
            └── schemas/
                └── fcm_token_schemas.py               ← [NEW] Schemas Pydantic

infra/
  └── database/
      └── models/
          └── user_fcm_token.py                        ← [NEW] Model SQLAlchemy

alembic/versions/
  └── XXX_create_user_fcm_tokens.py                    ← [NEW] Migration

tests/
  ├── unit/modules/notification/
  │   ├── test_register_fcm_token_use_case.py          ← [NEW]
  │   └── test_remove_fcm_token_use_case.py            ← [NEW]
  └── e2e/modules/notification/
      └── test_fcm_token_router.py                     ← [NEW]
```

---

## Parte 1 — Configuração do Firebase

### 1.1 Obter Credenciais no Firebase Console

1. Acesse **[console.firebase.google.com](https://console.firebase.google.com/)**.
2. Crie (ou selecione) um projeto.
3. Vá em **Project Settings** → aba **Service accounts**.
4. Clique em **Generate new private key** e baixe o arquivo `.json`.
5. **Nunca versione este arquivo no Git!** Adicione ao `.gitignore`:
   ```
   credentials/firebase-service-account.json
   ```

### 1.2 Instalar Dependência

```bash
uv add firebase-admin
```

### 1.3 Adicionar Variáveis ao `settings.py`

```python
# src/config/settings.py (MODIFICAR)
class Settings(BaseSettings):
    # ... campos existentes sem alteração ...

    # Firebase Cloud Messaging
    firebase_credentials_path: str = "credentials/firebase-service-account.json"
    # Alternativa: conteúdo JSON direto na env var (mais seguro em produção/CI)
    firebase_credentials_json: str = ""

    # Celery (usa redis_url como fallback)
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    @property
    def effective_celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def effective_celery_backend(self) -> str:
        return self.celery_result_backend or self.redis_url
```

### 1.4 `.env.example` (Adicionar)

```dotenv
# Firebase Cloud Messaging
FIREBASE_CREDENTIALS_PATH=credentials/firebase-service-account.json
# Ou via JSON inline (preferido em produção):
# FIREBASE_CREDENTIALS_JSON='{"type":"service_account","project_id":"...","private_key":"..."}'
```

---

## Parte 2 — Firebase Admin SDK (`infra/firebase/client.py`)

```python
# src/infra/firebase/client.py
import json
import os

import firebase_admin
from firebase_admin import credentials

from config.settings import settings


def _build_credentials() -> credentials.Base:
    """
    Constrói as credenciais do Firebase.

    Prioridade:
      1. FIREBASE_CREDENTIALS_JSON — conteúdo JSON inline (recomendado para produção/CI)
      2. FIREBASE_CREDENTIALS_PATH — caminho para arquivo .json (desenvolvimento local)
    """
    if settings.firebase_credentials_json:
        cred_dict = json.loads(settings.firebase_credentials_json)
        return credentials.Certificate(cred_dict)

    cred_path = settings.firebase_credentials_path
    if not os.path.exists(cred_path):
        raise FileNotFoundError(
            f"Firebase credentials file not found: {cred_path}. "
            "Set FIREBASE_CREDENTIALS_PATH or FIREBASE_CREDENTIALS_JSON."
        )
    return credentials.Certificate(cred_path)


def init_firebase() -> None:
    """
    Inicializa o Firebase Admin SDK.

    Idempotente: pode ser chamado múltiplas vezes sem erro
    (guarda protegido por firebase_admin._apps).
    Deve ser chamado:
      - No startup do worker Celery (via signal worker_process_init)
      - Opcionalmente no startup da API FastAPI
    """
    if not firebase_admin._apps:
        cred = _build_credentials()
        firebase_admin.initialize_app(cred)
```

> **Por que separar em uma função `init_firebase()`?**
> O Firebase Admin SDK deve ser inicializado **uma única vez** por processo.
> O Celery cria workers como processos separados (fork/spawn), portanto cada worker
> precisa chamar `init_firebase()` na sua inicialização, não apenas o processo da API.

---

## Parte 3 — Celery (`infra/tasks/celery_app.py`)

```python
# src/infra/tasks/celery_app.py
from celery import Celery
from celery.signals import worker_process_init

from config.settings import settings


celery_app = Celery(
    "classroom_tasks",
    broker=settings.effective_celery_broker,
    backend=settings.effective_celery_backend,
    include=["infra.tasks.notification_tasks"],
)

celery_app.conf.update(
    # Serialização
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Tempo
    timezone="America/Sao_Paulo",
    enable_utc=True,
    # Confiabilidade
    task_acks_late=True,             # Confirma a mensagem só após execução com sucesso
    task_reject_on_worker_lost=True, # Re-enfileira se o worker morrer no meio
    # Performance
    worker_prefetch_multiplier=4,    # Pré-carrega 4 tasks por worker (ajuste conforme carga)
)


@worker_process_init.connect
def init_worker(**kwargs: object) -> None:
    """
    Executado uma única vez quando cada processo worker é iniciado.
    Garante que o Firebase SDK esteja inicializado ANTES de qualquer task rodar.
    """
    from infra.firebase.client import init_firebase
    init_firebase()
```

> **Por que `task_acks_late=True`?**
> Com configuração padrão, o Celery confirma a mensagem da fila **ao receber** a task.
> Se o worker cair durante a execução, a mensagem é perdida.
> Com `acks_late=True`, a confirmação só ocorre após a execução bem-sucedida,
> garantindo que nenhuma notificação seja silenciosamente descartada.

---

## Parte 4 — Task de Notificação (`infra/tasks/notification_tasks.py`)

```python
# src/infra/tasks/notification_tasks.py
import logging
from celery import Task
from firebase_admin import messaging
from firebase_admin.exceptions import FirebaseError

from infra.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# FCM suporta no máximo 500 tokens por chamada de send_each_for_multicast
FCM_MAX_TOKENS_PER_BATCH = 500


def _chunk(lst: list, size: int) -> list[list]:
    """Divide uma lista em sublistas de tamanho máximo `size`."""
    return [lst[i : i + size] for i in range(0, len(lst), size)]


@celery_app.task(
    name="notification.send_attendance_opened",
    bind=True,
    max_retries=3,
    default_retry_delay=30,      # 30 segundos entre retries
    autoretry_for=(FirebaseError, ConnectionError, TimeoutError),
    retry_backoff=True,          # Espera exponencial: 30s, 60s, 120s
    retry_backoff_max=300,       # Máximo de 5 minutos entre retries
    retry_jitter=True,           # Adiciona aleatoriedade para evitar thundering herd
)
def send_attendance_opened_notification(
    self: Task,
    subject_class_name: str,
    day_code: str,
    duration_minutes: int,
    fcm_tokens: list[str],
) -> dict[str, int]:
    """
    Envia notificação push para todos os alunos de uma turma quando a chamada é aberta.

    Args:
        subject_class_name: Nome da turma (ex: "Programação Orientada a Objetos")
        day_code: Código do dia para confirmação de presença (ex: "X3KP7Q")
        duration_minutes: Duração da janela de confirmação em minutos
        fcm_tokens: Lista de FCM tokens dos alunos matriculados

    Returns:
        Dicionário com contagem de sucessos e falhas.
    """
    if not fcm_tokens:
        logger.info("send_attendance_opened_notification: no tokens, skipping.")
        return {"success_count": 0, "failure_count": 0}

    total_success = 0
    total_failure = 0

    for batch in _chunk(fcm_tokens, FCM_MAX_TOKENS_PER_BATCH):
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=f"📋 Chamada Aberta — {subject_class_name}",
                body=(
                    f"O professor iniciou a chamada! Você tem {duration_minutes} "
                    f"minutos. Código: {day_code}"
                ),
            ),
            # Dados extras acessíveis no app mesmo com o app em background
            data={
                "type": "ATTENDANCE_OPENED",
                "day_code": day_code,
                "subject_class_name": subject_class_name,
                "duration_minutes": str(duration_minutes),
            },
            android=messaging.AndroidConfig(
                priority="high",          # Alta prioridade — acorda o dispositivo
                ttl=duration_minutes * 60, # Expira junto com a chamada (TTL em segundos)
            ),
            apns=messaging.APNSConfig(
                headers={"apns-priority": "10"},
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(
                            title=f"📋 Chamada Aberta — {subject_class_name}",
                            body=(
                                f"O professor iniciou a chamada! Você tem {duration_minutes} "
                                f"minutos. Código: {day_code}"
                            ),
                        ),
                        sound="default",
                        badge=1,
                    )
                ),
            ),
            tokens=batch,
        )

        try:
            response = messaging.send_each_for_multicast(message)
            total_success += response.success_count
            total_failure += response.failure_count

            # Processar respostas e identificar tokens desinstalados / inválidos (UNREGISTERED)
            stale_tokens = []
            for idx, result in enumerate(response.responses):
                if not result.success:
                    error_code = getattr(result.exception, "code", "unknown")
                    logger.warning("FCM delivery failed for token index %d: %s", idx, error_code)
                    if error_code in ("registration-token-not-registered", "invalid-argument", "UNREGISTERED"):
                        stale_tokens.append(batch[idx])

            # Deletar do banco os tokens desinstalados/inválidos identificados
            if stale_tokens:
                # Exemplo: delete_stale_fcm_tokens_task.delay(stale_tokens)
                logger.info("Identificados %d tokens inativos/desinstalados para remoção.", len(stale_tokens))

        except FirebaseError as exc:
            logger.error("Firebase batch error: %s. Retrying...", exc)
            raise  # autoretry_for captura e re-enfileira

    logger.info(
        "Attendance opened notification: %d success, %d failure (total: %d tokens)",
        total_success, total_failure, len(fcm_tokens),
    )
    return {"success_count": total_success, "failure_count": total_failure}
```

---

## Parte 5 — Integração com `OpenAttendanceSessionUseCase`

O único ponto de integração entre o módulo de chamada e as notificações:

```python
# src/modules/attendance/application/use_cases/open_session.py (MODIFICAR)
import logging
from infra.tasks.notification_tasks import send_attendance_opened_notification

logger = logging.getLogger(__name__)


class OpenAttendanceSessionUseCase:

    async def execute(self, data: OpenAttendanceSessionInput) -> AttendanceSession:
        # ... todas as validações e criação de sessão sem alteração ...

        session = await self.session_repo.save(AttendanceSession(...))

        # Despachar notificação de forma assíncrona (best-effort)
        try:
            fcm_tokens = await self.enrollment_repo.find_active_fcm_tokens(
                data.subject_class_id
            )
            if fcm_tokens:
                send_attendance_opened_notification.delay(
                    subject_class_name=subject_class.name,
                    day_code=session.day_code,
                    duration_minutes=data.duration_minutes,
                    fcm_tokens=fcm_tokens,
                )
        except Exception:
            # Notificações são best-effort: falhar aqui NÃO deve cancelar a abertura da chamada.
            logger.exception(
                "Failed to enqueue attendance notification for session %s", session.id
            )

        return session
```

> **Por que `try/except` amplo aqui?**
> A abertura da chamada é a operação crítica de negócio.
> A notificação é **complementar** — se o Redis estiver temporariamente indisponível,
> o professor ainda deve conseguir abrir a chamada normalmente.
> Isso é uma decisão de design explícita chamada de **degradação graciosa (graceful degradation)**,
> não um mau uso do `except Exception`.

---

## Parte 6 — Endpoints de Gerenciamento de Tokens

### 6.1 Schema Pydantic

```python
# src/modules/notification/interface/schemas/fcm_token_schemas.py
from pydantic import BaseModel, Field


class RegisterFCMTokenRequest(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=64)
    fcm_token: str = Field(..., min_length=1)
    platform: str = Field(..., pattern="^(android|ios)$")
    app_version: str | None = Field(default=None, max_length=20)


class FCMTokenResponse(BaseModel):
    device_id: str
    platform: str
    updated_at: str  # ISO 8601

    model_config = {"from_attributes": True}
```

### 6.2 Endpoints

```
POST   /tenants/{tenant_id}/fcm-tokens              → Registra ou atualiza token FCM
DELETE /tenants/{tenant_id}/fcm-tokens/{device_id}  → Remove token ao fazer logout
```

**`POST /fcm-tokens`** — Chamado pelo app sempre que:
- O usuário faz login
- O Firebase SDK rotaciona o token (`onTokenRefresh` no Android / `didReceiveRegistrationToken` no iOS)

Operação é **idempotente**: faz UPSERT em `(user_id, device_id)`.

**`DELETE /fcm-tokens/{device_id}`** — Chamado no logout para evitar notificações
em dispositivos com sessão encerrada.

---

## Parte 7 — Validações de Negócio

### 7.1 Validações no `RegisterFCMTokenUseCase`

| Ordem | Validação | Exceção | HTTP |
|---|---|---|---|
| 1 | Tenant existe e não está deletado | `ResourceNotFoundException` | 404 |
| 2 | Usuário autenticado é membro do tenant | `ForbiddenException` | 403 |
| 3 | `platform` é `android` ou `ios` (validado pelo Pydantic `pattern`) | — | 422 |
| 4 | `device_id` e `fcm_token` não vazios (Pydantic `min_length=1`) | — | 422 |
| 5 | **Upsert** — cria ou atualiza o token do `(user_id, device_id)` | — (sem erro) | 200 |

> **Nota**: Não validamos se o `fcm_token` é de fato um token Firebase válido.
> A validação real ocorre no momento da entrega (tokens inválidos retornam erro
> na resposta do `send_each_for_multicast`). Validar antecipadamente exigiria uma
> chamada síncrona ao Firebase a cada login — custo injustificado.

### 7.2 Validações no `RemoveFCMTokenUseCase`

| Ordem | Validação | Exceção | HTTP |
|---|---|---|---|
| 1 | Tenant existe e não está deletado | `ResourceNotFoundException` | 404 |
| 2 | Usuário autenticado é membro do tenant | `ForbiddenException` | 403 |
| 3 | Token com `(user_id, device_id)` existe | `ResourceNotFoundException` | 404 |
| 4 | O token pertence ao usuário autenticado | `ForbiddenException` | 403 |

### 7.3 Validações da Task Celery

A task opera fora do ciclo HTTP. As "validações" são de infraestrutura:

| Situação | Comportamento |
|---|---|
| Lista de tokens vazia | Retorna imediatamente sem chamar o FCM |
| `FirebaseError` (ex: rede instável) | Re-tenta com backoff exponencial (até 3x, máx 5 min) |
| Token individual inválido (`UNREGISTERED`) | Loga o índice do token inválido; não falha o batch inteiro |
| Worker cai durante execução | Task é re-enfileirada (`acks_late=True`) |
| Redis indisponível ao despachar a task | `try/except` no use case absorve o erro graciosamente |
| Turma sem alunos matriculados com token | `find_active_fcm_tokens()` retorna lista vazia; task não é despachada |

---

## Parte 8 — Configuração do Ambiente de Desenvolvimento

### 8.1 Redis (já disponível no projeto)

O projeto já usa Redis para Rate Limiter. O Celery utilizará a mesma instância.

### 8.2 Adicionar Worker Celery ao `docker-compose.yml`

```yaml
  celery-worker:
    build: .
    command: >
      celery -A infra.tasks.celery_app worker
      --loglevel=info
      --concurrency=4
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - FIREBASE_CREDENTIALS_JSON=${FIREBASE_CREDENTIALS_JSON}
    depends_on:
      - redis
      - postgres
```

### 8.3 Rodar Localmente (sem Docker)

```bash
# Terminal 1: API FastAPI
uv run uvicorn src.main:app --reload

# Terminal 2: Worker Celery
uv run celery -A infra.tasks.celery_app worker --loglevel=info

# Terminal 3 (opcional): Celery Flower — painel de monitoramento em http://localhost:5555
uv run celery -A infra.tasks.celery_app flower --port=5555
```

**Celery Flower** exibe tasks em execução, concluídas, com falha e tempo médio de execução — essencial para debugar e demonstrar o fluxo assíncrono.

---

## Parte 9 — Testes

### 9.1 Estratégia

O FCM é uma dependência externa. Nos testes, **nunca chamamos a API real do Firebase**.

- **Testes Unitários**: Mockam a task Celery e o repositório de tokens.
- **Testes E2E**: Verificam que a task foi **despachada** (não entregue), usando `unittest.mock.patch`.

### 9.2 Testes Unitários dos Use Cases

**`test_register_fcm_token_use_case.py`**:
- Cria novo token com dados válidos → retorna token salvo.
- Atualiza token de mesmo `(user_id, device_id)` → upsert não cria duplicata.
- Falha `404` se tenant não encontrado.
- Falha `403` se usuário não é membro do tenant.

**`test_remove_fcm_token_use_case.py`**:
- Remove token existente com sucesso.
- Falha `404` se token não encontrado.
- Falha `403` se token pertence a outro usuário.

### 9.3 Testes E2E

**`test_fcm_token_router.py`**:
```python
async def test_register_fcm_token_e2e(client, session):
    """Aluno registra token FCM com sucesso."""
    # ...setup fixtures...
    res = await client.post(
        f"/tenants/{tenant.id}/fcm-tokens",
        json={
            "device_id": "device-uuid-abc123",
            "fcm_token": "fcm-token-xyz",
            "platform": "android",
            "app_version": "1.2.3",
        },
        headers=student_headers,
    )
    assert res.status_code == 200
    assert res.json()["device_id"] == "device-uuid-abc123"


async def test_register_fcm_token_upsert_e2e(client, session):
    """Registrar o mesmo device_id duas vezes atualiza o token sem criar duplicata."""
    # ...duas chamadas com mesmo device_id, fcm_tokens diferentes...
    # assert count(user_fcm_tokens) == 1
```

**`test_attendance_session_router.py`** — adicionar ao arquivo existente:
```python
from unittest.mock import patch

async def test_open_session_dispatches_notification_task(client, session):
    """Abertura de chamada deve despachar a task de notificação FCM."""
    with patch(
        "infra.tasks.notification_tasks.send_attendance_opened_notification.delay"
    ) as mock_delay:
        res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions",
            json={"room_id": room_id, "duration_minutes": 15},
            headers=prof_headers,
        )
        assert res.status_code == 201
        mock_delay.assert_called_once()
        call_kwargs = mock_delay.call_args.kwargs
        assert call_kwargs["day_code"] == res.json()["day_code"]
        assert call_kwargs["duration_minutes"] == 15
```

---

## Referências de Implementação

| Camada | Arquivo |
|---|---|
| Configuração Firebase | `src/infra/firebase/client.py` |
| Instância Celery | `src/infra/tasks/celery_app.py` |
| Task de Notificação | `src/infra/tasks/notification_tasks.py` |
| Ponto de Integração | `src/modules/attendance/application/use_cases/open_session.py` |
| Model SQLAlchemy | `src/infra/database/models/user_fcm_token.py` |
| Repositório | `src/modules/notification/infra/repositories/fcm_token_sqlalchemy_repository.py` |
| Endpoints | `src/modules/notification/interface/router.py` |
| Testes Unitários | `tests/unit/modules/notification/` |
| Testes E2E | `tests/e2e/modules/notification/test_fcm_token_router.py` |

---

## Ordem de Implementação

```
1.  uv add firebase-admin
2.  config/settings.py                              ← Adicionar firebase_credentials_* e celery_*
3.  .env.example                                    ← Documentar as novas variáveis
4.  infra/firebase/client.py                        ← Inicializador singleton
5.  infra/tasks/celery_app.py                       ← Instância Celery + worker_process_init
6.  infra/tasks/notification_tasks.py              ← Task com batching, retry, backoff
7.  infra/database/models/user_fcm_token.py        ← Model SQLAlchemy
8.  alembic/versions/XXX_create_user_fcm_tokens.py ← Migration
9.  notification/domain/entities/fcm_token.py      ← Entidade de domínio
10. notification/domain/repositories/              ← Protocol com upsert() e remove()
11. notification/infra/mappers/                    ← Mapper Model ↔ Entity
12. notification/infra/repositories/               ← Implementação SQLAlchemy (upsert)
13. notification/application/use_cases/register_fcm_token.py
14. notification/application/use_cases/remove_fcm_token.py
15. enrollment_repository.py                       ← Adicionar find_active_fcm_tokens()
16. enrollment_sqlalchemy_repository.py            ← Implementar find_active_fcm_tokens()
17. attendance/use_cases/open_session.py           ← Integrar .delay() com degradação graciosa
18. notification/interface/schemas/fcm_token_schemas.py
19. notification/interface/router.py
20. main.py                                        ← Registrar notification router
21. docker-compose.yml                             ← Adicionar serviço celery-worker
22. Testes unitários
23. Testes E2E (incluindo mock do dispatch no open_session)
```

---

## Checklist de Implementação

- [ ] `uv add firebase-admin`
- [ ] Adicionar `firebase_credentials_path`, `firebase_credentials_json` e configs Celery ao `settings.py`
- [ ] Criar `infra/firebase/client.py` com `init_firebase()` idempotente
- [ ] Criar `infra/tasks/celery_app.py` com signal `worker_process_init`
- [ ] Criar `infra/tasks/notification_tasks.py` com batching de 500 tokens, retries e backoff exponencial
- [ ] Criar `infra/database/models/user_fcm_token.py` com `UNIQUE(user_id, device_id)`
- [ ] Criar migration Alembic para `user_fcm_tokens`
- [ ] Criar entidade `FCMToken` em domínio
- [ ] Criar `FCMTokenRepository` Protocol com `upsert()` e `remove()`
- [ ] Criar mapper e implementação SQLAlchemy (upsert via `ON CONFLICT DO UPDATE`)
- [ ] Criar `RegisterFCMTokenUseCase` e `RemoveFCMTokenUseCase`
- [ ] Adicionar `find_active_fcm_tokens(subject_class_id)` ao `EnrollmentRepository`
- [ ] Integrar task dispatch em `OpenAttendanceSessionUseCase` com degradação graciosa
- [ ] Criar schemas Pydantic e router de notificações
- [ ] Registrar router em `main.py`
- [ ] Adicionar serviço `celery-worker` ao `docker-compose.yml`
- [ ] Testes unitários de `RegisterFCMTokenUseCase` e `RemoveFCMTokenUseCase`
- [ ] Testes E2E do router de tokens
- [ ] Teste E2E de despacho de task ao abrir chamada (via mock de `.delay()`)
