# Task 6 — Módulo de Chamada (`Attendance`)

> **Objetivo**: Implementar o sistema de chamada acadêmica com validação dupla: código do dia + geolocalização.
> A sessão de chamada é aberta pelo professor, e **múltiplos alunos podem confirmar presença simultaneamente**
> dentro da janela de tempo configurável. A arquitetura é projetada para suportar alta concorrência sem
> duplicidade de registros.
>
> **Entrega esperada desta etapa**:
>
> - `POST /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions` — professor abre chamada
> - `GET /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions` — lista sessões da turma
> - `GET /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions/{session_id}` — detalhe da sessão
> - `PATCH /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions/{session_id}/close` — professor encerra chamada manualmente
> - `POST /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions/{session_id}/confirm` — aluno confirma presença
> - `GET /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions/{session_id}/records` — listar registros de presença (com filtro por `record_status`)
> - `GET /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions/{session_id}/records/{record_id}` — detalhe de um registro
> - `PATCH /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions/{session_id}/records/{record_id}/review` — professor aprova ou rejeita registro irregular

> [!WARNING]
> **Fora do escopo desta etapa — adicionados em versões futuras:**
>
> - 🔔 **Notificações push via Firebase Cloud Messaging (FCM)**: quando a chamada é aberta, os alunos matriculados serão notificados via FCM. Isso exige a integração com Celery + Redis e o SDK do Firebase. Ficará para a etapa de notificações.
> - 📷 **Evidência fotográfica**: o campo `evidence_photo_url` existe no banco mas **não será populado nesta etapa**. O upload de imagens para S3/MinIO e o envio da foto pelo aluno serão adicionados na etapa de armazenamento de evidências.
> - 🔐 **Device security avançada**: detecção de GPS spoofing, verificação de mock location ativo e bloqueio de requisições fora de app mobile legítimo serão abordados na etapa de segurança. Os campos de device fingerprint (`device_id`, `ip_address`, `user_agent`, `device_info`) **já existem no banco desde esta etapa** para não requerer migration futura.

---

## Conceito Central — Sessão + Registro de Presença

O módulo de chamada é composto por **duas entidades** que separam responsabilidades distintas:

| Entidade            | Pergunta respondida                                     | Cardinalidade              |
| ------------------- | ------------------------------------------------------- | -------------------------- |
| `AttendanceSession` | **"Quando aconteceu a aula e qual a janela de tempo?"** | 1 por chamada aberta       |
| `AttendanceRecord`  | **"Quem estava presente nessa chamada?"**               | N por sessão (1 por aluno) |

Essa separação é o **padrão de mercado** (Canvas LMS, Moodle, Google Classroom) e permite:

- Consultar frequência de um aluno sem varrer dados de outras turmas.
- Auditar cada confirmação individualmente (timestamp, coordenadas, distância calculada).
- Reprocessar sessões sem perder os registros individuais.

---

## Diagrama de Relacionamentos

```
tenants
  └── subject_classes
          ├── room_id ──────────────────────────────► rooms
          │                                              └── location (GEOGRAPHY Point)
          │                                              └── tolerance_radius_meters
          └── attendance_sessions (1:N)
                  ├── room_id ──────────────────────► rooms (sala do dia — pode ser diferente da sala padrão)
                  ├── day_code
                  ├── opened_at / expires_at / status
                  └── attendance_records (1:N)
                          ├── tenant_member_id ────► tenant_members
                          ├── student_location (GEOGRAPHY Point)
                          ├── distance_meters (calculado via PostGIS)
                          ├── within_radius (boolean)
                          └── UNIQUE(session_id, tenant_member_id) → impede duplicidade
```

---

## Modelagem do Banco de Dados

### `attendance_sessions` — A Sessão/Janela de Chamada

```
attendance_sessions
  ├── id                  UUID (PK)
  ├── subject_class_id    FK → subject_classes.id  ON DELETE CASCADE
  ├── room_id             FK → rooms.id            ON DELETE SET NULL
  ├── day_code            VARCHAR(10)
  ├── opened_at           TIMESTAMPTZ DEFAULT now()
  ├── expires_at          TIMESTAMPTZ
  ├── closed_at           TIMESTAMPTZ nullable
  ├── status              ENUM (open | closed)     DEFAULT open
  ├── created_at          TIMESTAMPTZ DEFAULT now()
  └── updated_at          TIMESTAMPTZ
```

> **Por que `room_id` na sessão e não só na turma?**
> A turma (`SubjectClass`) já tem um `room_id` padrão, mas no dia da aula o professor pode estar
> em outra sala (troca de sala, laboratório, etc.). A sessão carrega o `room_id` do
> **local real do dia**, cujas coordenadas serão usadas para a validação geoespacial.

### `attendance_records` — O Registro Individual de Presença

```
attendance_records
  ├── id                   UUID (PK)
  ├── session_id           FK → attendance_sessions.id  ON DELETE CASCADE
  ├── tenant_member_id     FK → tenant_members.id       ON DELETE CASCADE
  ├── confirmed_at         TIMESTAMPTZ DEFAULT now()
  │
  ├── ── Geolocalização ──────────────────────────────────────────────────
  ├── student_location     GEOGRAPHY(Point, 4326)     ← coordenadas brutas do dispositivo
  ├── distance_meters      FLOAT                      ← calculado via ST_Distance
  ├── within_radius        BOOLEAN                    ← distance_meters ≤ tolerance_radius_meters
  ├── gps_accuracy_meters  FLOAT nullable             ← precisão relatada pelo app (opcional)
  │
  ├── ── Auditoria de Irregularidades ────────────────────────────────────
  ├── record_status        ENUM (regular|irregular|approved|rejected)  DEFAULT regular
  ├── irregularity_flags   TEXT[]                     ← array PostgreSQL com flags disparadas
  ├── reviewed_by          FK → tenant_members.id nullable
  ├── reviewed_at          TIMESTAMPTZ nullable
  ├── review_note          TEXT nullable              ← observação do professor ao revisar
  │
  ├── ── Device Fingerprint (anti-fraude) ─────────────────────────────────
  ├── device_id            VARCHAR(64) nullable       ← UUID gerado pelo app, persistido no device
  ├── ip_address           INET nullable              ← tipo nativo PostgreSQL para IPv4/IPv6
  ├── user_agent           TEXT nullable              ← header HTTP — detecta scripts/curl
  ├── device_info          JSONB nullable             ← { platform, os_version, model, app_version }
  │
  ├── evidence_photo_url   TEXT nullable              ← reservado para etapa futura
  └── UNIQUE(session_id, tenant_member_id)            ← constraint anti-duplicidade
```

> **Invariante de domínio**: Um aluno só pode ter **1 registro de presença por sessão**.
> Garantido em três camadas:
>
> 1. Validação no use case antes de inserir.
> 2. Constraint `UNIQUE(session_id, tenant_member_id)` no banco.
> 3. Teste cobrindo tentativa duplicada simultânea.

---

## Status da Sessão — Máquina de Estados

```
                  professor abre chamada
[inexistente] ──────────────────────────► [open]
                                              │
                              ┌───────────────┴───────────────────┐
                              │                                   │
                    expires_at alcançado               professor fecha manualmente
                     (automático)                      PATCH .../close
                              │                                   │
                              ▼                                   ▼
                           [closed] ◄──────────────────────── [closed]
```

**Regras de transição:**

- `open → closed`: única transição permitida. Uma sessão **nunca volta para `open`**.
- Confirmações só são aceitas quando `status = open` E `now() < expires_at`.
- A verificação do `expires_at` é feita **no use case** (fail fast).

---

## Enum `SessionStatus`

```python
# src/shared/enums/session_status.py
from enum import Enum

class SessionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
```

---

## Enum `RecordStatus` — Máquina de Estados de Auditoria

O `record_status` separa três responsabilidades distintas:

- O **dado bruto** (o que o aluno enviou — nunca muda)
- O **resultado da validação automática** (calculado pelo sistema no momento da confirmação)
- A **decisão humana** (professor ou admin revisando irregularidades)

```python
# src/shared/enums/record_status.py
from enum import Enum

class RecordStatus(str, Enum):
    REGULAR   = "regular"   # Tudo ok — nenhuma flag disparada. Presença conta automaticamente.
    IRREGULAR = "irregular" # Uma ou mais flags disparadas. Presença SUSPENSA até revisão.
    APPROVED  = "approved"  # Professor revisou e aprovou. Presença conta.
    REJECTED  = "rejected"  # Professor revisou e rejeitou. Presença não conta.
```

**Máquina de estados:**

```
                     confirmação sem flags
[confirmed] ──────────────────────────────────────► [regular]
     │                                                   (presença conta automaticamente)
     │
     │               confirmação com flags
     └──────────────────────────────────────────────► [irregular]
                                                          │
                                          ┌───────────────┴────────────────┐
                                          │                                │
                               professor aprova                  professor rejeita
                               PATCH .../review                  PATCH .../review
                                          │                                │
                                          ▼                                ▼
                                      [approved]                      [rejected]
                              (presença conta)               (presença não conta)
```

> **Importante**: `regular` e `irregular` são definidos **automaticamente** pelo sistema
> no momento da inserção. `approved` e `rejected` são definidos **manualmente** pelo professor/admin.
> Um registro `regular` **nunca precisa** de revisão humana.

---

## Irregularidades — `irregularity_flags`

As flags são strings armazenadas em um array PostgreSQL (`TEXT[]`). São calculadas automaticamente
no use case `confirm_attendance.py` imediatamente após o cálculo da distância:

| Flag | Descrição | Critério de disparo |
|---|---|---|
| `outside_radius` | Aluno confirmou fora do raio geográfico da sala | `distance_meters > tolerance_radius_meters` |
| `low_gps_accuracy` | Precisão do GPS maior que o raio da sala — localização matematicamente inconclusiva | `gps_accuracy_meters > tolerance_radius_meters` (se enviado pelo app) |
| `confirmed_near_expiry` | Confirmou nos últimos 30s antes da chamada expirar — suspeito de receber o código de fora | `(expires_at - confirmed_at).total_seconds() < 30` |
| `non_mobile_client` | `user_agent` não corresponde a app iOS/Android — possível script ou curl | `user_agent` analisado no request |
| `shared_device` | Mesmo `device_id` já confirmou presença de **outro aluno** nessa sessão — um confirmou pelo outro | consulta em `attendance_records` da mesma sessão por `device_id` |

> `multiple_failed_codes` (brute force no `day_code`) requer uma tabela auxiliar `attendance_code_attempts`
> para ser detectado — implementação futura se necessário.

### Lógica de classificação automática no use case

```python
# modules/attendance/application/use_cases/confirm_attendance.py
# Executado após calcular distance_meters e within_radius:

from datetime import datetime, timezone

flags: list[str] = []

# 1. Fora do raio geográfico
if not within_radius:
    flags.append("outside_radius")

# 2. GPS impreciso (se o app enviou a precisão)
if gps_accuracy_meters and gps_accuracy_meters > room.tolerance_radius_meters:
    flags.append("low_gps_accuracy")

# 3. Confirmação perto do prazo de expiração (threshold configurável, padrão: 30s)
remaining_seconds = (session.expires_at - datetime.now(timezone.utc)).total_seconds()
if remaining_seconds < 30:
    flags.append("confirmed_near_expiry")

# 4. Cliente não-mobile (detectado pelo user_agent do request)
if user_agent and not is_mobile_user_agent(user_agent):
    flags.append("non_mobile_client")

# 5. Dispositivo já usado por outro aluno nessa sessão
if device_id:
    existing = await record_repo.find_by_device_id_in_session(session_id, device_id)
    if existing and existing.tenant_member_id != current_tenant_member_id:
        flags.append("shared_device")

record_status = RecordStatus.IRREGULAR if flags else RecordStatus.REGULAR
```

---

## Auditoria — Endpoints para Professor/Admin

### Listar registros com filtro por status

```
GET /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions/{session_id}/records
    ?record_status=irregular     ← filtra os que precisam de revisão
    ?record_status=regular       ← apenas os regulares
    (sem filtro)                 ← retorna todos
```

**Response** (lista):
```json
[
  {
    "id": "uuid",
    "student_name": "João Silva",
    "confirmed_at": "2026-08-31T14:13:47Z",
    "distance_meters": 87.3,
    "within_radius": false,
    "gps_accuracy_meters": 45.0,
    "record_status": "irregular",
    "irregularity_flags": ["outside_radius", "low_gps_accuracy"],
    "reviewed_by": null,
    "reviewed_at": null,
    "review_note": null
  }
]
```

### Aprovar ou rejeitar um registro irregular

```
PATCH /tenants/{tenant_id}/subject-classes/{subject_class_id}
      /attendance-sessions/{session_id}/records/{record_id}/review
```

**Quem pode chamar**: `PROFESSOR` da turma ou `ADMIN` do tenant.

**Payload**:
```json
{
  "decision": "approved",
  "note": "Aluno estava no corredor próximo à sala, GPS impreciso confirmado."
}
```

**Validações**:
1. Registro existe e pertence à sessão.
2. `record_status` é `irregular` — só registros irregulares podem ser revisados.
3. Usuário tem permissão.

**Processamento**:
1. Setar `record_status = approved | rejected`.
2. Setar `reviewed_by = current_tenant_member_id`.
3. Setar `reviewed_at = now()`.
4. Setar `review_note` se enviado.

**Visão conceitual do painel do professor**:
```
Chamada — Turma POO — 31/08/2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 35 presenças regulares
⚠️  3 irregulares (aguardando revisão)
❌  2 ausentes

─── Irregulares ──────────────────────────────────
João Silva   87m da sala   [Aprovar] [Rejeitar]
  Flags: fora do raio, GPS impreciso (±45m)

Maria Souza  12m da sala   [Aprovar] [Rejeitar]
  Flags: confirmou nos últimos 8 segundos

Pedro Lima   342m da sala  [Aprovar] [Rejeitar]
  Flags: fora do raio, dispositivo compartilhado
```

---

## Device Fingerprint — Campos Capturados Nesta Etapa

Os campos de device fingerprint são **coletados e persistidos nesta etapa**, mas a lógica de
segurança avançada (ex: bloqueio de requisições fora de app mobile, detecção de GPS spoofing)
será implementada em etapa futura.

| Campo | Origem | Como capturar | Para que serve |
|---|---|---|---|
| `device_id` | App mobile | UUID gerado pelo app na primeira instalação, persistido no Keychain/Keystore | Detectar `shared_device` — mesmo device confirmando dois alunos |
| `ip_address` | Backend | `request.client.host` (FastAPI/Starlette) | Correlacionar confirmações suspeitas do mesmo IP |
| `user_agent` | Backend | `request.headers.get("user-agent")` | Detectar `non_mobile_client` (scripts, curl, etc.) |
| `device_info` | App mobile | JSON com `platform`, `os_version`, `model`, `app_version` | Auditoria e análise de padrões |

```python
# No endpoint confirm (interface/router.py), capturar do request:
ip_address = request.client.host
user_agent = request.headers.get("user-agent")
# device_id e device_info vêm no payload do app
```

> **Por que já persistir agora?** Campos adicionados posteriormente exigem migration de banco
> em produção — arriscado e trabalhoso. Adicionar os campos agora (aceitando `null` se o app
> não enviar) evita esse custo futuro e já permite as flags `non_mobile_client` e `shared_device`
> sem dependências externas.

---

## Fluxo Técnico Detalhado

### Abertura da Chamada (Professor)

**Endpoint**: `POST /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions`

**Quem pode chamar**: `PROFESSOR` da turma ou `ADMIN` do tenant.

**Payload**:

```json
{
  "room_id": "uuid-da-sala",
  "duration_minutes": 15
}
```

**Validações (em ordem)**:

1. Tenant existe e não está deletado.
2. `SubjectClass` existe, não está deletada, e pertence ao tenant.
3. Usuário autenticado é o `professor_id` da turma **ou** tem role `ADMIN` no tenant.
4. `room_id` pertence ao mesmo tenant e não está deletada.
5. **Não existe outra sessão com `status = open` para essa turma** → impede duas chamadas abertas ao mesmo tempo. Retorna `409` se existir.
6. `duration_minutes` deve ser positivo (validado pelo schema Pydantic).

**Processamento**:

1. Gerar `day_code` — string de 6 caracteres alfanuméricos (maiúsculos, sem `0`, `O`, `I`, `1`).
2. Calcular `expires_at = now() + timedelta(minutes=duration_minutes)`.
3. Persistir `AttendanceSession` com `status = open`.
4. _(Futuro — FCM)_ Disparar task Celery para notificar alunos.

**Resposta `201 Created`**:

```json
{
  "id": "uuid",
  "subject_class_id": "uuid",
  "room_id": "uuid",
  "day_code": "X3KP7Q",
  "opened_at": "2026-08-31T14:00:00Z",
  "expires_at": "2026-08-31T14:15:00Z",
  "status": "open"
}
```

---

### Confirmação de Presença (Aluno) — Ponto Crítico de Concorrência

**Endpoint**: `POST /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions/{session_id}/confirm`

**Quem pode chamar**: `ALUNO` matriculado (`EnrollmentStatus.ACTIVE`) na turma.

**Payload**:

```json
{
  "day_code": "X3KP7Q",
  "latitude": -23.55052,
  "longitude": -46.633308
}
```

**Validações — executadas sequencialmente (fail fast)**:

| Ordem | Validação                                                   | Exceção                     | HTTP |
| ----- | ----------------------------------------------------------- | --------------------------- | ---- |
| 1     | Tenant existe e não está deletado                           | `ResourceNotFoundException` | 404  |
| 2     | `SubjectClass` existe e não está deletada                   | `ResourceNotFoundException` | 404  |
| 3     | `AttendanceSession` existe para essa turma                  | `ResourceNotFoundException` | 404  |
| 4     | Sessão está `OPEN`                                          | `BusinessRuleException`     | 409  |
| 5     | `now() < expires_at`                                        | `BusinessRuleException`     | 409  |
| 6     | `day_code` enviado == `session.day_code` (case-insensitive) | `BusinessRuleException`     | 400  |
| 7     | Aluno tem matrícula `ACTIVE` nessa turma                    | `ForbiddenException`        | 403  |
| 8     | Aluno ainda não confirmou presença nessa sessão             | `BusinessRuleException`     | 409  |
| 9     | Coordenadas válidas (lat ∈ [-90,90], lon ∈ [-180,180])      | Schema Pydantic             | 422  |

**Processamento da Geolocalização**:

```
1. Montar GEOGRAPHY Point do aluno:
   student_point = f"SRID=4326;POINT({longitude} {latitude})"
   ATENÇÃO: ordem é longitude, latitude (X, Y) — erro clássico inverter.

2. Buscar coordenadas da sala (rooms.location) via JOIN com a sessão.

3. Calcular distância via PostGIS:
   distance_meters = ST_Distance(room.location, student_point)
   → ST_Distance em GEOGRAPHY já retorna metros (sem conversão manual)

4. Verificar se está dentro do raio:
   within_radius = distance_meters <= room.tolerance_radius_meters
   → NÃO bloqueia a confirmação se estiver fora do raio.
   → Registra com within_radius=False e flag "outside_radius".

5. Calcular irregularity_flags e definir record_status:
   → Ver seção "Irregularidades" abaixo.
   → record_status = IRREGULAR se flags, REGULAR caso contrário.
```

> **Por que não rejeitar quem está fora do raio?**
> GPS em ambientes fechados tem imprecisão de 10–50m em condições normais.
> Rejeitar automaticamente criaria falsos negativos inaceitáveis. O padrão de mercado
> (Google Maps, Uber, sistemas universitários sérios) é **registrar o dado bruto**
> e permitir revisão humana. A flag `outside_radius` sinaliza a irregularidade
> sem punir automaticamente o aluno.

**Controle de Concorrência** (múltiplos alunos confirmando simultaneamente):

```
Camada 1 — Use Case (aplicação):
  → Busca se já existe AttendanceRecord para (session_id, tenant_member_id)
  → Se existir, lança BusinessRuleException("presença já confirmada")
  → Resolve a maioria dos casos

Camada 2 — Banco (constraint UNIQUE):
  → Se dois requests do mesmo aluno passarem pela validação ao mesmo tempo
    (race condition), o banco rejeita a segunda inserção com IntegrityError
  → O repository captura IntegrityError e trata como
    BusinessRuleException("presença já confirmada")
```

> Essa é a **Opção A** descrita na documentação técnica: Constraint UNIQUE + tratamento de erro.
> Adequada para o caso de uso (evitar duplicidade de presença do mesmo aluno),
> sem overhead de fila ou locking explícito.
> Para o TCC: demonstrar sem proteção (duplicidades) → com proteção (0 duplicatas).

**Inserção no banco** — distância e `within_radius` calculados diretamente via PostGIS:

```sql
INSERT INTO attendance_records
  (session_id, tenant_member_id, student_location, distance_meters, within_radius,
   gps_accuracy_meters, record_status, irregularity_flags,
   device_id, ip_address, user_agent, device_info)
VALUES
  (:session_id, :tenant_member_id,
   ST_GeographyFromText('SRID=4326;POINT(:lon :lat)'),
   ST_Distance(
     (SELECT location FROM rooms WHERE id = :room_id),
     ST_GeographyFromText('SRID=4326;POINT(:lon :lat)')
   ),
   ST_DWithin(
     (SELECT location FROM rooms WHERE id = :room_id),
     ST_GeographyFromText('SRID=4326;POINT(:lon :lat)'),
     :tolerance_radius_meters
   ),
   :gps_accuracy_meters, :record_status, :irregularity_flags,
   :device_id, :ip_address, :user_agent, :device_info
  )
```

**Resposta `201 Created`**:

```json
{
  "id": "uuid",
  "session_id": "uuid",
  "confirmed_at": "2026-08-31T14:03:22Z",
  "distance_meters": 23.5,
  "within_radius": true,
  "record_status": "regular",
  "irregularity_flags": []
}
```

---

### Encerramento Manual da Chamada (Professor)

**Endpoint**: `PATCH /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions/{session_id}/close`

**Quem pode chamar**: `PROFESSOR` da turma ou `ADMIN` do tenant.

**Validações**:

1. Sessão existe e pertence à turma.
2. Sessão está `OPEN` (se já `CLOSED`, retorna `409`).
3. Usuário tem permissão.

**Processamento**: Setar `status = closed` e `closed_at = now()`.

---

## Controle de Erros

| Situação                                                | Exceção                                    | HTTP |
| ------------------------------------------------------- | ------------------------------------------ | ---- |
| Tenant não encontrado                                   | `ResourceNotFoundException`                | 404  |
| `SubjectClass` não encontrada ou deletada               | `ResourceNotFoundException`                | 404  |
| `AttendanceSession` não encontrada                      | `ResourceNotFoundException`                | 404  |
| Já existe sessão `open` para a turma                    | `BusinessRuleException`                    | 409  |
| Sessão está `closed` (tentativa de confirmar)           | `BusinessRuleException`                    | 409  |
| Sessão expirada (`expires_at` no passado)               | `BusinessRuleException`                    | 409  |
| `day_code` inválido                                     | `BusinessRuleException`                    | 400  |
| Aluno sem matrícula `active` na turma                   | `ForbiddenException`                       | 403  |
| Presença já confirmada nessa sessão                     | `BusinessRuleException`                    | 409  |
| `latitude` ou `longitude` fora do range válido          | Schema Pydantic                            | 422  |
| Usuário sem permissão para abrir/fechar                 | `ForbiddenException`                       | 403  |
| Sala não encontrada ou não pertence ao tenant           | `ResourceNotFoundException`                | 404  |
| Race condition: dois inserts simultâneos do mesmo aluno | `IntegrityError` → `BusinessRuleException` | 409  |

---

## Arquitetura do Módulo — Clean Architecture

```
src/
├── shared/
│   └── enums/
│       ├── session_status.py                          ← 1. Enum SessionStatus (open | closed)
│       └── record_status.py                           ← 2. Enum RecordStatus (regular|irregular|approved|rejected)
│
├── infra/
│   └── database/
│       └── models/
│           ├── attendance_session.py                  ← 3. Model SQLAlchemy AttendanceSessionModel
│           └── attendance_record.py                   ← 4. Model SQLAlchemy AttendanceRecordModel
│
└── modules/
    └── attendance/
        ├── domain/
        │   ├── entities/
        │   │   ├── attendance_session.py              ← 5. Entidade domínio AttendanceSession
        │   │   └── attendance_record.py               ← 6. Entidade domínio AttendanceRecord
        │   └── repositories/
        │       ├── attendance_session_repository.py   ← 7. Protocol do repositório de sessão
        │       └── attendance_record_repository.py    ← 8. Protocol do repositório de registro
        │
        ├── application/
        │   └── use_cases/
        │       ├── open_session.py                    ← 9.  OpenAttendanceSessionUseCase
        │       ├── close_session.py                   ← 10. CloseAttendanceSessionUseCase
        │       ├── confirm_attendance.py              ← 11. ConfirmAttendanceUseCase (geoloc + flags)
        │       ├── review_record.py                   ← 12. ReviewAttendanceRecordUseCase (aprovar/rejeitar)
        │       ├── list_records.py                    ← 13. ListAttendanceRecordsUseCase (com filtro de status)
        │       ├── get_record.py                      ← 14. GetAttendanceRecordUseCase
        │       ├── get_session.py                     ← 15. GetAttendanceSessionUseCase
        │       └── list_sessions.py                   ← 16. ListAttendanceSessionsUseCase
        │
        ├── infra/
        │   ├── mappers/
        │   │   ├── attendance_session_mapper.py       ← 17. Mapper Model ↔ Entity (sessão)
        │   │   └── attendance_record_mapper.py        ← 18. Mapper Model ↔ Entity (registro)
        │   └── repositories/
        │       ├── session_sqlalchemy_repository.py   ← 19. Implementação SQLAlchemy (sessão)
        │       └── record_sqlalchemy_repository.py    ← 20. Implementação SQLAlchemy + PostGIS
        │
        └── interface/
            ├── router.py                              ← 21. Router HTTP com 8 endpoints
            └── schemas/
                ├── session_schemas.py                 ← 22. Schemas Pydantic (sessão)
                └── record_schemas.py                  ← 23. Schemas Pydantic (registro + review)

alembic/versions/
  └── XXX_create_attendance_tables.py                  ← 24. Migration (duas tabelas + índice GiST)

tests/
  ├── unit/modules/attendance/
  │   ├── test_open_session_use_case.py
  │   ├── test_close_session_use_case.py
  │   ├── test_confirm_attendance_use_case.py          ← inclui testes de flags de irregularidade
  │   └── test_review_record_use_case.py
  ├── integration/modules/attendance/
  │   └── test_attendance_sqlalchemy_repository.py
  └── e2e/modules/attendance/
      ├── test_attendance_session_router.py
      ├── test_attendance_record_router.py             ← listar, detalhar, revisar registros
      └── test_attendance_concurrency.py              ← N confirmações simultâneas do mesmo aluno
```

---

## Detalhes da Geolocalização com PostGIS

### Por que `GEOGRAPHY` e não `GEOMETRY`?

| Tipo        | Plano de coordenadas  | `ST_Distance` retorna                  |
| ----------- | --------------------- | -------------------------------------- |
| `GEOMETRY`  | Plano cartesiano (2D) | Graus decimais (inútil para metros)    |
| `GEOGRAPHY` | Esfera (Terra real)   | **Metros** (automático, sem conversão) |

O projeto já usa `Geography(geometry_type="POINT", srid=4326)` na tabela `rooms` (ver `room.py`).
As mesmas configurações devem ser usadas em `attendance_records.student_location`.

### Implementação no Repositório

```python
# record_sqlalchemy_repository.py
from geoalchemy2.functions import ST_Distance, ST_GeographyFromText, ST_DWithin

# ATENÇÃO: ordem é LONGITUDE, LATITUDE (X, Y) — não latitude, longitude
student_point = ST_GeographyFromText(f"SRID=4326;POINT({longitude} {latitude})")

distance_expr = ST_Distance(room_location, student_point)
within_radius_expr = ST_DWithin(room_location, student_point, tolerance_radius)
```

### Índice Espacial na Migration

```sql
-- Já deve existir na migration da tabela rooms.
-- Criar aqui se ainda não existir:
CREATE INDEX IF NOT EXISTS idx_rooms_location
ON rooms USING GIST(location);
```

---

## Geração do `day_code`

```python
import secrets

# Exclui caracteres ambíguos: 0 (zero), O (letra), 1 (um), I (i maiúsculo)
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

def generate_day_code(length: int = 6) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))
```

> **`secrets` vs `random`**: `secrets` é criptograficamente seguro, adequado para geração
> de códigos de acesso, mesmo que a validade seja curta.

---

## Ordem de Implementação

```
1.  shared/enums/session_status.py
2.  shared/enums/record_status.py
3.  infra/database/models/attendance_session.py
4.  infra/database/models/attendance_record.py          ← com todos os campos de auditoria e fingerprint
5.  alembic/versions/XXX_create_attendance_tables.py
6.  modules/attendance/domain/entities/attendance_session.py
7.  modules/attendance/domain/entities/attendance_record.py
8.  modules/attendance/domain/repositories/attendance_session_repository.py
9.  modules/attendance/domain/repositories/attendance_record_repository.py
10. modules/attendance/infra/mappers/attendance_session_mapper.py
11. modules/attendance/infra/mappers/attendance_record_mapper.py
12. modules/attendance/infra/repositories/session_sqlalchemy_repository.py
13. modules/attendance/infra/repositories/record_sqlalchemy_repository.py  ← PostGIS + device fingerprint
14. modules/attendance/application/use_cases/open_session.py
15. modules/attendance/application/use_cases/close_session.py
16. modules/attendance/application/use_cases/confirm_attendance.py         ← classifica flags automaticamente
17. modules/attendance/application/use_cases/review_record.py              ← aprovar/rejeitar irregulares
18. modules/attendance/application/use_cases/list_records.py
19. modules/attendance/application/use_cases/get_record.py
20. modules/attendance/application/use_cases/get_session.py
21. modules/attendance/application/use_cases/list_sessions.py
22. modules/attendance/interface/schemas/session_schemas.py
23. modules/attendance/interface/schemas/record_schemas.py                 ← inclui ReviewRequest/Response
24. modules/attendance/interface/router.py
25. src/main.py (registrar router)
26. tests/unit/...
27. tests/integration/...
28. tests/e2e/... (incluindo concorrência e fluxo de revisão de irregulares)
```

---

## Testes Esperados

### Unitários

**`test_open_session_use_case.py`**

- Cria sessão com `status=open` e `day_code` de 6 chars.
- Falha `409` se já existe sessão `open` para a turma.
- Falha `403` se usuário não é professor da turma nem admin.
- Falha `404` se turma ou sala não encontrada.

**`test_close_session_use_case.py`**

- Seta `status=closed` e `closed_at`.
- Falha `409` se sessão já está `closed`.
- Falha `403` se usuário não tem permissão.

**`test_confirm_attendance_use_case.py`**

- Confirmação dentro do raio → `within_radius=True`, `record_status=regular`, `flags=[]`.
- Confirmação fora do raio → registra com `within_radius=False`, `flags=["outside_radius"]`, `record_status=irregular`.
- GPS impreciso (`gps_accuracy_meters > tolerance_radius`) → flag `low_gps_accuracy` + `record_status=irregular`.
- Confirmação nos últimos 30s → flag `confirmed_near_expiry` + `record_status=irregular`.
- `user_agent` não-mobile → flag `non_mobile_client` + `record_status=irregular`.
- Mesmo `device_id` de outro aluno na sessão → flag `shared_device` + `record_status=irregular`.
- Falha `409` se sessão está `closed`.
- Falha `409` se `expires_at` no passado.
- Falha `400` se `day_code` incorreto.
- Falha `403` se aluno não tem matrícula `active`.
- Falha `409` se aluno já confirmou presença.
- `IntegrityError` é capturado e tratado como `409`.

**`test_review_record_use_case.py`**

- Aprovar registro `irregular` → `record_status=approved`, `reviewed_by` e `reviewed_at` preenchidos.
- Rejeitar registro `irregular` → `record_status=rejected`.
- Falha `409` ao tentar revisar registro `regular` (não necessita revisão).
- Falha `403` se usuário não é professor da turma nem admin.

### E2E — Teste de Concorrência

```python
# tests/e2e/modules/attendance/test_attendance_concurrency.py
# Disparar N requests simultâneos do MESMO aluno para a mesma sessão.
# Resultado esperado: 1 registro criado, os demais retornam 409.
```

---

## Checklist de Implementação

- [ ] `shared/enums/session_status.py`
- [ ] `shared/enums/record_status.py`
- [ ] `infra/database/models/attendance_session.py`
- [ ] `infra/database/models/attendance_record.py` (com campos de auditoria e device fingerprint)
- [ ] Migration Alembic (duas tabelas)
- [ ] `domain/entities/attendance_session.py`
- [ ] `domain/entities/attendance_record.py`
- [ ] `domain/repositories/attendance_session_repository.py` (Protocol)
- [ ] `domain/repositories/attendance_record_repository.py` (Protocol)
- [ ] `infra/mappers/attendance_session_mapper.py`
- [ ] `infra/mappers/attendance_record_mapper.py`
- [ ] `infra/repositories/session_sqlalchemy_repository.py`
- [ ] `infra/repositories/record_sqlalchemy_repository.py` (PostGIS + device fingerprint)
- [ ] `application/use_cases/open_session.py`
- [ ] `application/use_cases/close_session.py`
- [ ] `application/use_cases/confirm_attendance.py` (classifica flags automaticamente)
- [ ] `application/use_cases/review_record.py` (aprovar/rejeitar irregulares)
- [ ] `application/use_cases/list_records.py`
- [ ] `application/use_cases/get_record.py`
- [ ] `application/use_cases/get_session.py`
- [ ] `application/use_cases/list_sessions.py`
- [ ] `interface/schemas/session_schemas.py`
- [ ] `interface/schemas/record_schemas.py` (inclui ReviewRequest/Response)
- [ ] `interface/router.py`
- [ ] Registrar router em `main.py`
- [ ] Testes unitários
- [ ] Testes de integração
- [ ] Testes E2E (incluindo concorrência e fluxo de revisão)
