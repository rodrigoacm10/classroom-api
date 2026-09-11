# Chamada ao vivo (web)

**Quem:** professor, admin. **Objetivo:** abrir a janela, mostrar o código do dia, ver quem confirmou.

Núcleo do produto. Artboard Paper: **1440×900**, dentro do shell.

## Regiões

1. **Cabeçalho da sessão:** turma (`subject_class.name` + `discipline_name`), sala, `status`
2. **Código do dia:** `day_code` em destaque. Countdown até `expires_at`
3. **Ações:** “Encerrar chamada”, “Cancelar” (dialogs)
4. **Métricas curtas:** total de records, quantos `within_radius`, quantos `irregular`
5. **Tabela ao vivo:** horário, aluno (ver nota), distância, raio, status, ação Revisar

Abrir chamada (se não houver `open`): dialog `duration_minutes` (default 15) + select sala opcional.

## Dados

- Abrir: `POST /tenants/{tenant_id}/subject-classes/{subject_class_id}/attendance-sessions`  
  `{ room_id?, duration_minutes }`
- Sessão: `GET .../attendance-sessions/{session_id}` → `day_code`, `status`, `opened_at`, `expires_at`, `subject_class`, `room`
- Lista sessões: `GET .../attendance-sessions`
- Records: `GET .../attendance-sessions/{session_id}/records`  
  → `confirmed_at`, `distance_meters`, `within_radius`, `record_status`, `irregularity_flags`, `evidence_photo_url`
- Encerrar: `PATCH .../{session_id}/close`
- Cancelar: `PATCH .../{session_id}/cancel`
- Revisar: `PATCH .../records/{record_id}/review` `{ decision, note }`
- Schema: `session_schemas.py`, `record_schemas.py`

**Nota:** o record traz `tenant_member_id`, não o nome. A UI deve resolver nome via matrículas da turma (`GET .../enrollments`) até a API expor o nome no record. No Paper, mostrar nome fictício + comment de binding.

Poll da lista de records enquanto `status = open` (intervalo ~5s). Não desenhar websocket.

## Estados

- Sem sessão aberta: empty + “Abrir chamada”
- Aberta: código visível; tabela pode estar vazia (“Nenhum aluno confirmou ainda.”)
- `irregular`: ação Revisar (`approved` / `rejected` + nota)
- Foto: só se `evidence_photo_url`; senão “—”
- Encerrada/cancelada: esconder o código; ação para abrir nova sessão

## Não mostrar

`device_id`, `ip_address`, `user_agent`, `device_info`, `gps_accuracy_meters` na tabela principal (podem ir num drawer de detalhe do record, se necessário para auditoria).
