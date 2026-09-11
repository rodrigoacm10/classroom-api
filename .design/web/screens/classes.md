# Turmas (web)

**Quem:** professor, admin, coordenador. **Objetivo:** achar uma turma e entrar no detalhe.

## Regiões

- Título “Turmas” + primary “Nova turma”
- Tabela: disciplina, turma, sala (nome se houver), ações (abrir)
- Dialog criar: `discipline_name`, `name`, select `room_id`

## Dados

- Lista: `GET /tenants/{tenant_id}/subject-classes` → `discipline_name`, `name`, `room_id`
- Criar: `POST .../subject-classes` `{ room_id, name, discipline_name }`
- Salas no select: `GET /tenants/{tenant_id}/rooms` → `id`, `name`
- Schema: `src/modules/subject_class/interface/schemas/subject_class_schemas.py`

Detalhe da turma (mesma página ou rota filha): abas Matrículas | Chamadas | Relatório.

## Estados

- Vazio: “Nenhuma turma.” + CTA criar
- Delete (admin): confirm dialog; `DELETE` 204

## Não mostrar

`professor_id`, `tenant_id`, timestamps.
