---
topic: "Visão geral do Locus, papéis e navegação"
routes:
  - "/dashboard"
  - "/dashboard/perfil"
  - "/tenants"
allowed_roles:
  - "ALL"
---

# Visão Geral do Locus e Papéis de Acesso

## O que é o Locus

O **Locus** é uma plataforma de controle de presença acadêmica por geolocalização (geofencing). Em vez da chamada em papel ou de hardware dedicado (catracas e biometria), o professor abre uma chamada ao vivo no painel web, o sistema gera um código de 6 caracteres e uma janela de tempo, e os alunos confirmam a presença pelo aplicativo móvel usando o código e o GPS do aparelho.

O painel web foi feito para professores, coordenadores e administradores gerenciarem salas, turmas, chamadas ao vivo, auditoria de presença e relatórios de frequência.

## Papéis e permissões no sistema

O Locus possui quatro papéis dentro de uma instituição (tenant):

- **Administrador (`admin`)**: gestão completa da instituição — configurações, membros, envio e revogação de convites, cadastro de salas, turmas, matrículas, abertura/auditoria de chamadas e relatórios.
- **Coordenador (`coordenador`)**: acompanhamento acadêmico — consulta turmas, alunos, chamadas, relatórios e acessa áreas de coordenação da instituição.
- **Professor (`professor`)**: conduz as próprias turmas — cadastra e configura salas, cria/gerencia turmas e matrículas, abre e encerra chamadas ao vivo, audita presenças irregulares e gera relatórios de frequência.
- **Aluno (`aluno`)**: utiliza o aplicativo móvel para receber avisos de chamada, confirmar presença com código + GPS (e foto opcional) e acompanhar o próprio histórico.

Se um usuário tentar abrir uma rota restrita ao seu papel (por exemplo, um professor acessando `/dashboard/convites`), o sistema exibe aviso de acesso negado.

## Como alternar de instituição ou acessar seu perfil

Uma mesma conta no Locus pode participar de mais de uma instituição de ensino.

1. No canto inferior esquerdo da barra lateral, clique no **card com seu nome e papel** para abrir o menu da conta.
2. Para ver seus dados cadastrais e segurança da conta, clique em **Meu Perfil** (`/dashboard/perfil`).
3. Para trocar de faculdade/instituição ativa sem fazer logout, clique em **Alternar Instituição** (`/tenants`) e selecione a instituição desejada.
4. Para encerrar a sessão com segurança, clique em **Sair da conta**.

## Tela inicial (Início)

A tela **Início** (`/dashboard`) exibe o resumo rápido das suas atividades na instituição ativa, incluindo acesso direto a chamadas ativas, turmas e indicadores recentes.
