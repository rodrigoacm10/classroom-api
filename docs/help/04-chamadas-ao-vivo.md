---
topic: "Chamadas ao vivo: abrir, acompanhar e encerrar"
routes:
  - "/dashboard/chamadas"
  - "/dashboard/chamadas/nova"
allowed_roles:
  - "admin"
  - "coordenador"
  - "professor"
---

# Chamadas ao Vivo

## Como abrir uma nova chamada

A abertura de chamadas é permitida para **Professores (`professor`)** e **Administradores (`admin`)**.

1. No menu lateral, clique em **Chamadas** (`/dashboard/chamadas`) e depois em **Nova chamada** — ou acesse diretamente `/dashboard/chamadas/nova`.
2. Selecione a **turma** para a qual deseja realizar a chamada.
3. Escolha o **local da chamada**:
   - Use a **sala vinculada à turma** (opção mais rápida); ou
   - Selecione outra **sala avulsa** cadastrada na instituição; ou
   - Defina uma localização personalizada no preview do mapa em tempo real, caso a aula seja em um local temporário.
4. Defina a **janela de tempo** (duração em minutos durante a qual os alunos poderão confirmar presença).
5. Clique em **Abrir chamada**.

Assim que a chamada é aberta:
- O Locus gera automaticamente um **código de 6 caracteres** para exibição em sala (projetor ou quadro).
- Todos os alunos matriculados que ativaram notificações no aplicativo Android recebem um **aviso push** informando que a chamada está aberta.

## Como funciona a confirmação pelo aluno

Com a chamada aberta, o aluno abre o aplicativo móvel do Locus, digita o **código de 6 caracteres** e envia a confirmação com sua localização GPS (e foto de evidência opcional, se configurada).

A API aceita a confirmação quando:
1. A chamada ainda está **aberta** dentro da janela de tempo;
2. O **código de 6 caracteres** confere;
3. A **matrícula** do aluno na turma está ativa;
4. O aluno ainda não confirmou presença nessa chamada (o banco impede confirmações duplicadas).

## Como acompanhar e encerrar uma chamada ao vivo

1. Após abrir a chamada (ou clicando em uma chamada ativa em `/dashboard/chamadas`), você acompanha em tempo real (`/dashboard/chamadas/[subjectClassId]/[sessionId]`) quem já confirmou presença, quem está pendente e eventuais alertas de localização.
2. Quando o tempo limite expira, um processo em segundo plano **encerra a chamada automaticamente**.
3. Se quiser finalizar antes do prazo (ou cancelar uma chamada aberta por engano), utilize os botões de **Encerrar chamada** ou **Cancelar chamada** na própria tela da sessão ao vivo.
