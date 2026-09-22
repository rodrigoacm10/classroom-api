# Validações da Confirmação de Presença — `POST /confirm`

Este documento descreve todas as validações e regras de negócio que ocorrem quando um aluno executa a confirmação de presença via o endpoint:

```
POST /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions/{session_id}/confirm
```

---

## Payload da Requisição

```json
{
  "day_code": "X3KP7Q",
  "latitude": -8.04761,
  "longitude": -34.87701,
  "gps_accuracy_meters": 15.5,
  "device_id": "a3f2c1d4-8b7e-4f2a-9c3d-1e5f6a7b8c9d",
  "device_info": {
    "platform": "android",
    "os_version": "14",
    "app_version": "1.2.3",
    "model": "Samsung Galaxy S23",
    "timezone": "America/Sao_Paulo"
  }
}
```

> O `ip_address` e o `user_agent` são capturados automaticamente pelo backend a partir dos headers HTTP da requisição — o app **não precisa enviá-los**.

---

## Parte 1 — Validações Bloqueantes (Fail-Fast)

Executadas em sequência antes de qualquer escrita no banco. Se qualquer uma falhar, a requisição é interrompida imediatamente com a resposta de erro correspondente.

| Ordem | Validação | Detalhe | HTTP se falhar |
|---|---|---|---|
| 1 | **Existência do Tenant** | Verifica se a instituição existe e não está com `deleted = True`. | `404 Not Found` |
| 2 | **Existência da Turma** | Verifica se a `SubjectClass` pertence ao tenant e está ativa (`deleted = False`). | `404 Not Found` |
| 3 | **Existência da Sessão** | Verifica se a `AttendanceSession` pertence àquela turma. | `404 Not Found` |
| 4 | **Status da Sessão — CANCELLED** | A chamada foi cancelada pelo professor. Confirmação não é possível. | `409 Conflict` |
| 5 | **Status da Sessão — CLOSED/OPEN** | A chamada foi encerrada manualmente antes do tempo. Confirmação não é possível. | `409 Conflict` |
| 6 | **Janela de Expiração (`expires_at`)** | O horário limite passou (`now >= expires_at`). A chamada expirou automaticamente. | `409 Conflict` |
| 7 | **Código do Dia (`day_code`)** | O código de 6 dígitos enviado pelo aluno não coincide com o da sessão. A comparação é case-insensitive. | `400 Bad Request` |
| 8 | **Vínculo Institucional** | O usuário autenticado (JWT) não é membro da instituição. | `403 Forbidden` |
| 9 | **Matrícula Ativa** | O aluno não possui matrícula com `status = ACTIVE` naquela turma específica. | `403 Forbidden` |
| 10 | **Bloqueio de Duplicidade (Aplicação)** | O aluno já possui um `AttendanceRecord` registrado para essa sessão. | `409 Conflict` |
| 11 | **Bloqueio de Duplicidade (Banco — Race Condition)** | Proteção via constraint SQL `UNIQUE (session_id, tenant_member_id)`. Garante integridade mesmo em requisições simultâneas do mesmo aluno. | `409 Conflict` |

---

## Parte 2 — Device Fingerprinting & Metadados de Auditoria

Após passar por todas as validações bloqueantes, o sistema coleta e analisa os metadados do dispositivo para classificar a presença como `REGULAR` ou `IRREGULAR`.

### 2.1 `device_id` — Identificador Único do Dispositivo

| | |
|---|---|
| **Origem** | Enviado pelo app mobile no corpo da requisição (campo `device_id`). |
| **Geração** | O app gera um UUID persistente na primeira instalação e o armazena em local seguro (`Keychain` no iOS, `Keystore` no Android). |
| **Armazenamento** | Coluna `device_id VARCHAR(64)` na tabela `attendance_records`. |
| **Validação Ativa?** | **SIM** — gera flag de irregularidade. |

**Regra de Detecção — Flag `shared_device`:**

O sistema verifica se o mesmo `device_id` já foi utilizado para confirmar a presença de **outro aluno diferente** na mesma sessão de chamada.

```python
# confirm_attendance.py
if data.device_id:
    shared_rec = await self.record_repo.find_by_device_id_in_session(
        data.session_id, data.device_id
    )
    if shared_rec and shared_rec.tenant_member_id != member.id:
        flags.append("shared_device")
```

| Cenário | Resultado |
|---|---|
| `device_id` nunca visto nesta sessão. | ✅ Sem flag. |
| `device_id` já registrou presença do **mesmo aluno** (re-tentativa). | Bloqueado na validação 10 (duplicidade). |
| `device_id` já registrou presença de **outro aluno** nesta sessão. | ⚠️ Flag `shared_device` → Status `IRREGULAR`. |

> **Limitação:** O `device_id` pode ser resetado pelo usuário ao reinstalar o aplicativo. Resolve ~90% dos casos de fraude amadora.

---

### 2.2 `device_info` — Metadados do Hardware

| | |
|---|---|
| **Origem** | Enviado pelo app mobile no corpo da requisição (campo `device_info`, objeto JSON). |
| **Armazenamento** | Coluna `device_info JSONB` na tabela `attendance_records`. |
| **Validação Ativa?** | **NÃO** — apenas armazenamento para auditoria manual ou análises futuras. |

**Campos recomendados:**

```json
{
  "platform": "android",
  "os_version": "14",
  "app_version": "1.2.3",
  "model": "Samsung Galaxy S23",
  "timezone": "America/Sao_Paulo"
}
```

O formato JSONB foi escolhido por ser flexível (o app pode adicionar novos campos sem migração de banco) e pesquisável (`device_info->>'platform' = 'android'`).

---

### 2.3 `ip_address` — Endereço IP de Origem

| | |
|---|---|
| **Origem** | Capturado automaticamente pelo backend (`request.client.host` no FastAPI/Starlette). |
| **Armazenamento** | Coluna `ip_address INET` na tabela `attendance_records`. O tipo `INET` do PostgreSQL suporta nativamente IPv4 e IPv6. |
| **Validação Ativa?** | **NÃO** — apenas armazenamento para auditoria. **Nenhuma flag é gerada a partir do IP.** |

**Motivo para não validar:**  
Em um ambiente universitário, todos os alunos na mesma rede Wi-Fi da instituição compartilham o mesmo IP público de saída. Uma validação baseada em IP geraria um número inaceitável de falsos positivos, bloqueando alunos legítimos.

O IP é mantido como dado de auditoria para investigações manuais pelo professor ou administrador.

---

### 2.4 `user_agent` — Agente HTTP do Cliente

| | |
|---|---|
| **Origem** | Capturado automaticamente pelo backend do header HTTP `User-Agent`. |
| **Armazenamento** | Coluna `user_agent TEXT` na tabela `attendance_records`. |
| **Validação Ativa?** | **SIM** — gera flag de irregularidade. |

**Regra de Detecção — Flag `non_mobile_client`:**

O sistema verifica se o `User-Agent` da requisição corresponde ao padrão de um aplicativo mobile legítimo (iOS/Android).

```python
# confirm_attendance.py
MOBILE_UA_KEYWORDS = ["okhttp", "dart", "cfnetwork", "android", "iphone", "ipad", "mobile"]

def is_mobile_user_agent(ua: str | None) -> bool:
    if not ua:
        return False
    return any(k in ua.lower() for k in MOBILE_UA_KEYWORDS)

# ...
if data.user_agent and not is_mobile_user_agent(data.user_agent):
    flags.append("non_mobile_client")
```

| Exemplo de `User-Agent` | Resultado |
|---|---|
| `okhttp/4.9.0` (SDK Android) | ✅ Mobile legítimo. Sem flag. |
| `Dart/3.0 (dart:io)` (Flutter) | ✅ Mobile legítimo. Sem flag. |
| `CFNetwork/1474 Darwin/23.0.0` (iOS) | ✅ Mobile legítimo. Sem flag. |
| `Mozilla/5.0 (Windows NT 10.0...)` (Chrome no PC) | ⚠️ Flag `non_mobile_client` → Status `IRREGULAR`. |
| `curl/8.0.1` ou `python-requests/2.31` | ⚠️ Flag `non_mobile_client` → Status `IRREGULAR`. |
| `null` / ausente | ⚠️ Flag `non_mobile_client` → Status `IRREGULAR`. |

---

## Parte 3 — Flags de Irregularidade (Antifraude Automático)

Todas as flags são acumulativas. O registro recebe status `IRREGULAR` se **ao menos uma flag** for disparada.

| Flag | Condição de disparo | Tipo de Dado Avaliado |
|---|---|---|
| `outside_radius` | Distância GPS do aluno até a sala > raio de tolerância (metros). Calculado via PostGIS `ST_Distance`. | Geolocalização |
| `low_gps_accuracy` | Precisão do GPS (`gps_accuracy_meters`) > raio de tolerância da sala. Localização inconclusiva. | Geolocalização |
| `confirmed_near_expiry` | Confirmação realizada nos últimos **30 segundos** antes do encerramento da chamada. | Tempo |
| `non_mobile_client` | `User-Agent` HTTP não corresponde a um aplicativo iOS/Android legítimo. | `user_agent` |
| `shared_device` | Mesmo `device_id` registrou presença de **outro aluno diferente** na mesma sessão. | `device_id` |

---

## Parte 4 — Status Final do Registro

| Situação | `record_status` | Próximo passo |
|---|---|---|
| Nenhuma flag disparada. | `REGULAR` | Presença computada automaticamente. Nenhuma ação necessária. |
| Uma ou mais flags disparadas. | `IRREGULAR` | O professor é notificado e pode revisar manualmente. |
| Professor revisa e aprova. | `APPROVED` | Presença computada (equivale a `REGULAR`). |
| Professor revisa e rejeita. | `REJECTED` | Presença não computada (equivale a falta). |

---

## Referências de Implementação

| Camada | Arquivo |
|---|---|
| Caso de Uso Principal | [`confirm_attendance.py`](../src/modules/attendance/application/use_cases/confirm_attendance.py) |
| Entidade de Domínio | [`attendance_record.py`](../src/modules/attendance/domain/entities/attendance_record.py) |
| Repositório (PostGIS + Savepoints) | [`record_sqlalchemy_repository.py`](../src/modules/attendance/infra/repositories/record_sqlalchemy_repository.py) |
| Schema da Requisição | [`record_schemas.py`](../src/modules/attendance/interface/schemas/record_schemas.py) |
| Testes Unitários | [`test_confirm_attendance_use_case.py`](../tests/unit/modules/attendance/test_confirm_attendance_use_case.py) |
| Testes E2E | [`test_attendance_record_router.py`](../tests/e2e/modules/attendance/test_attendance_record_router.py) |
| Testes de Concorrência | [`test_attendance_concurrency.py`](../tests/e2e/modules/attendance/test_attendance_concurrency.py) |
