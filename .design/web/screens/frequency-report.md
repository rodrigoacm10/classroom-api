# Relatório de frequência (web)

**Quem:** professor, admin. **Objetivo:** ver a turma e quem está em risco.

## Regiões

- Título + primary “Gerar relatório”
- Resumo: `total_students`, `class_average_frequency`, `students_at_risk`
- Tabela de alunos: nome, presentes, faltas, irregulares, frequência, `at_risk`, distância média
- Clique na row → detalhe do aluno (mesmos campos, um card)

## Dados

- Turma: `POST /tenants/{tenant_id}/subject-classes/{subject_class_id}/reports/frequency`
- Aluno: `GET .../reports/frequency/{tenant_member_id}`
- Schema: `src/modules/report/interface/schemas/report_schemas.py`  
  `frequency_rate` (0–1 ou 0–100: formatar como % na UI), `at_risk`, `avg_distance_meters`, `confirmations_near_limit`

## Estados

- Loading longo (cálculo paralelo): “Gerando relatório…” no botão; não deixar clicar de novo
- Vazio: turma sem matrículas / sem sessões — mensagem clara
- `at_risk`: destacar na lista; opcional ordenar esses no topo

## Não mostrar

`strategy_used`, `workers_used`, `duration_ms` (interno/TCC; não é UI de professor).
