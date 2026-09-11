# Mobile — shell

App do aluno. Artboard Paper: **390×844** (iPhone), mais um **360×800** se quiser Android compacto depois — não no primeiro passe.

## Estrutura autenticada

```text
┌─────────────────────────┐
│ Instituição · role      │  56px (top)
├─────────────────────────┤
│                         │
│     conteúdo            │
│                         │
├─────────────────────────┤
│ Início  Histórico  Conta│  56px + safe area
└─────────────────────────┘
```

- Sem mais de 3 tabs.
- Auth (login, instituição, convite): **sem tabs**, stack full screen.

## Permissões nativas (não são telas)

GPS na confirmação; câmera só se houver evidência; push após `switch-tenant`. Falha de permissão: copy no fluxo de confirmar, não um tutorial genérico.
