---
topic: "Relatórios de frequência, alunos abaixo de 75% e exportação"
routes:
  - "/dashboard/relatorios"
allowed_roles:
  - "admin"
  - "coordenador"
  - "professor"
---

# Relatórios de Frequência

## O que o relatório de frequência mostra

A área de **Relatórios** (`/dashboard/relatorios`) consolida a frequência de uma turma inteira com base em todas as chamadas encerradas. Para cada aluno matriculado, o relatório apresenta:

- **Total de presenças**, **faltas** (incluindo presenças rejeitadas na auditoria) e **registros irregulares**;
- **Taxa de frequência (%)** da turma e de cada aluno;
- **Indicador de risco (< 75%)**: destaca automaticamente quais alunos estão **abaixo de 75% de frequência** (em risco de reprovação por falta);
- **Métricas geoespaciais**: distância média (em metros) das confirmações do aluno até o ponto da sala e quantidade de confirmações próximas ao limite do raio.

## Como gerar um relatório de frequência

1. No menu lateral, clique em **Relatórios** (`/dashboard/relatorios`).
2. Selecione a **turma** desejada.
3. Clique em **Gerar relatório** para calcular as estatísticas consolidadas da turma.
4. Utilize os filtros ou a ordenação na tabela para identificar rapidamente os alunos marcados **em risco (abaixo de 75%)**.

## Como exportar o relatório

Na tela de **Relatórios** (`/dashboard/relatorios`), após gerar o relatório da turma, utilize o botão de **Exportar** disponível no topo da visualização para baixar os dados para uso administrativo ou secretaria acadêmica.

## Sobre a regra de 75% e presenças rejeitadas

- Presenças **rejeitadas** na auditoria são contabilizadas como **falta**.
- Alunos cuja taxa de frequência fica **abaixo de 75%** são sinalizados automaticamente como **em risco** no relatório consolidado da turma.
- O processamento do cálculo geoespacial roda em paralelo no servidor para gerar rapidamente relatórios mesmo em turmas grandes.
