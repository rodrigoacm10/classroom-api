# Confirmar presença (mobile)

**Quem:** aluno matriculado. **Objetivo:** enviar código + GPS dentro da janela.

Núcleo do produto. Artboard **390×844**.

## Regiões

1. Turma + sala (`session.subject_class`, `session.room`)
2. Tempo restante (`expires_at`)
3. Input `day_code` (6 caracteres)
4. Status GPS: “Obtendo localização…” / precisão se `gps_accuracy_meters` / erro de permissão
5. Primary “Confirmar presença” (habilitado com código + coords)
6. Evidência foto: só se o produto exigir no v1; senão omitir (campo `evidence_photo_url` é response, não input nesta rota)

## Dados

- Sessão: `GET .../attendance-sessions/{session_id}` — não exibir `day_code` da response para o aluno (o código é do professor). UI pede o código; não pré-preencher com o da API.
- Confirmar: `POST .../attendance-sessions/{session_id}/confirm`  
  `{ day_code, latitude, longitude, gps_accuracy_meters?, device_id? }`
- Schema: `record_schemas.py` (`ConfirmAttendanceRequest`, `AttendanceRecordResponse`)

Sucesso: resultado com `record_status`, `within_radius`, `distance_meters`.  
`irregular`: “Registrado com pendência; o professor pode revisar.”

## Estados

- Sessão não `open`: “Esta chamada não está mais aberta.”
- Sem GPS: bloquear submit, CTA configurações
- 400 negócio (código, raio, duplicata): mensagem do `detail`
- Loading no botão; não enviar duas vezes

## Não mostrar

`day_code` da sessão, `ip_address`, `user_agent`, `device_info`, `irregularity_flags` crus (traduzir se um dia a API documentar labels).
