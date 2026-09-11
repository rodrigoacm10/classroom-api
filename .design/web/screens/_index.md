# Web — telas

Cartões em `screens/`. Status: **brief** = mapeado à API, ainda sem artboard no Paper.

| Tela | Arquivo | Papel | Prioridade |
|---|---|---|---|
| Login | `login.md` | público | 1 |
| Instituição | `select-tenant.md` | autenticado | 1 |
| Turmas | `classes.md` | prof/admin | 2 |
| Chamada ao vivo | `attendance-live.md` | prof/admin | **1 (núcleo)** |
| Relatório | `frequency-report.md` | prof/admin | 2 |
| Salas | `rooms.md` | prof/admin | 3 |
| Matrículas | `enrollments.md` | prof/admin | 3 |
| Equipe | `team.md` | admin | 3 |
| Convite (aceite) | `accept-invite.md` | público/auth | 3 |

Cadastro (`POST /users/`) e recuperar senha reutilizam o card de login (mesmo layout, outros campos). Sem arquivo extra.
