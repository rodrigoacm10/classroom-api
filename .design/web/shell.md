# Web — shell

Painel para professor/admin/coordenador. Artboard Paper: **1440×900**.

## Estrutura

```text
┌──────────┬────────────────────────────────────────┐
│ Brand    │ Instituição ▾     usuário     Sair     │  56px
│          ├────────────────────────────────────────┤
│ Turmas   │                                        │
│ Salas    │           conteúdo da rota             │
│ Equipe*  │                                        │
│          │                                        │
└──────────┴────────────────────────────────────────┘
  240px
```

\* Equipe só com `role = admin`.

- Topbar: seletor de instituição (`GET /tenants/me` + `POST /auth/switch-tenant`). Mostrar `name` + `role`.
- Em viewport estreita: sidebar vira drawer.

## Auth fora do shell

Login, cadastro, forgot/reset, aceite de convite e escolha de instituição: layout central, sem sidebar.
