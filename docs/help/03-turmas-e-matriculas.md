---
topic: "Turmas e matrículas de alunos"
routes:
  - "/dashboard/turmas"
  - "/dashboard/turmas/nova"
  - "/dashboard/alunos"
allowed_roles:
  - "admin"
  - "coordenador"
  - "professor"
---

# Turmas e Matrículas de Alunos

## Como funcionam as turmas no Locus

Uma **turma** conecta uma disciplina a um **professor responsável**, uma **sala padrão** (com geofence configurado) e os **alunos matriculados**. Ao abrir uma chamada para a turma, apenas os alunos com matrícula ativa nessa turma conseguem confirmar presença e recebem a notificação no aplicativo.

## Como criar uma nova turma

1. No menu lateral, clique em **Turmas** (`/dashboard/turmas`).
2. Clique em **Nova turma** (`/dashboard/turmas/nova`).
3. Preencha os dados principais da turma (nome/disciplina, código ou período) e vincule a **sala padrão** onde as aulas acontecem.
4. Salve a turma. Você será direcionado para a gestão da turma (`/dashboard/turmas/[id]`).

## Como editar uma turma

1. Acesse **Turmas** (`/dashboard/turmas`) e selecione a turma desejada.
2. Clique em **Editar** (`/dashboard/turmas/[id]/editar`) para atualizar informações ou trocar a sala vinculada.

## Como matricular alunos em uma turma

1. Abra os detalhes da turma em **Turmas** → clique na turma (`/dashboard/turmas/[id]`).
2. Na aba ou seção de **Matrículas / Alunos**, adicione os alunos que já pertencem à instituição.
3. Somente alunos com **matrícula ativa** na turma poderão confirmar presença nas chamadas daquela disciplina.

Se o aluno ainda não tiver conta na instituição, um **Administrador** precisa enviar um convite antes (veja a área de Convites).

## Como consultar o histórico de um aluno

1. No menu lateral, clique em **Alunos** (`/dashboard/alunos`) para visualizar a listagem de estudantes da instituição.
2. Clique em um aluno específico (`/dashboard/alunos/[id]`) para consultar suas turmas matriculadas e métricas individuais de presença.
