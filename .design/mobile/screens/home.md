# Início (mobile)

**Quem:** aluno. **Objetivo:** ver turmas e se há chamada aberta.

## Regiões

- Lista de turmas matriculadas
- Em cada item: disciplina/turma + indicador “Chamada aberta” se existir sessão `open`
- Tap → confirmar presença (se aberta) ou detalhe/histórico da turma

## Dados

- Matrículas: `GET /tenants/{tenant_id}/members/{member_id}/enrollments` → `subject_class_id`, `status`
- Por turma: `GET .../subject-classes/{id}/attendance-sessions` — destacar `status = open`
- Schema: `enrollment_schemas.py`, `session_schemas.py`

**Nota:** enrollment não traz nome da turma. Resolver com `GET .../subject-classes/{id}` (`name`, `discipline_name`). No Paper, mostrar os dois textos.

Só `status = active` na home. `dropped` fica no histórico ou some.

## Estados

- Vazio: “Você não está em nenhuma turma.”
- Nenhuma chamada aberta: lista normal, sem o indicador
- Erro de GPS depois: não nesta tela

## Não mostrar

IDs, `drop_reason`.
