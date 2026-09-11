# Matrículas (web)

**Quem:** professor, admin. **Objetivo:** ver quem está na turma e matricular.

Vive no detalhe da turma (aba).

## Regiões

- Primary “Matricular aluno”
- Tabela: aluno, `status`, `enrolled_at`
- Admin: trancar (`PATCH` drop) vs remover erro (`DELETE`) — dois verbos, confirm dialogs diferentes

## Dados

- `GET/POST /tenants/{tenant_id}/subject-classes/{id}/enrollments`
- Body criar: `{ tenant_member_id }`
- Schema: `enrollment_schemas.py`

**Nota:** response não traz nome do aluno. Resolver membro/usuário no Paper com nome fictício; binding = `tenant_member_id`.

## Não mostrar

`deleted_at` (salvo admin com `include_deleted`).
