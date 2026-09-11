# Histórico (mobile)

**Quem:** aluno. **Objetivo:** ver presenças/faltas por turma.

## Regiões

- Filtro por turma (matrículas)
- Lista de sessões: data `opened_at`, status se confirmou / faltou / irregular
- Risco: **só quando a API expuser isso ao aluno**

## Dados

- Sessões: `GET .../subject-classes/{id}/attendance-sessions`
- Record do aluno: `GET .../sessions/{id}/records` filtrado pelo próprio `tenant_member_id` (a API lista todos os records da sessão; no app, mostrar só o do usuário. Se isso for vazamento de dados, é gap de backend — no Paper desenhar só o item do aluno)

`GET .../reports/frequency/{tenant_member_id}` hoje exige professor/admin. **Não** usar no app do aluno até existir endpoint próprio. Sem inventar % de frequência no mock como se viesse da API.

## Não mostrar

Lista completa da turma, distâncias de colegas, `strategy_used`.
