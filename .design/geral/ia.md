# Arquitetura de informação

Dois clientes, um backend. Papel (`role`) vem do JWT depois de `POST /auth/switch-tenant`.

Contexto de produto (o que é o Locus, objetivos, glossário): `.design/geral/produto.md`.

## Superfícies

| Cliente | Quem | Stack prevista |
|---|---|---|
| **Web** | Professor, Admin, Coordenador | React |
| **Mobile** | Aluno (professor pode logar, mas o núcleo do app é presença) | React Native |

## Papéis

| Role | Web | Mobile |
|---|---|---|
| `professor` | Turmas, salas, chamada, revisão, relatório | Opcional: ver turmas; confirmar não é o fluxo |
| `admin` | Tudo do professor + membros, convites, excluir sala/turma | Pouco uso |
| `coordenador` | Relatórios (mesmo shell; ações de chamada ocultas se a API recusar) | Pouco uso |
| `aluno` | Fora de escopo do painel | Home, confirmar, histórico |

Nav **não mostra** item que a API restringe com `require_role`. Em dúvida, esconda.

## Fluxo de entrada (os dois clientes)

1. Login — `POST /auth/login` (`client_type`: `web` ou `mobile`)
2. Instituições — `GET /tenants/me`
3. Entrar na instituição — `POST /auth/switch-tenant` `{ tenant_id }`
4. Shell autenticado daquela tenant

Cadastro: `POST /users/`. Recuperar senha: `POST /auth/forgot-password` → `POST /auth/reset-password`.  
Convite: link público `GET /invites/{token}` → logado `POST /invites/{token}/accept`.

Push (mobile, sem tela própria): `POST /tenants/{tenant_id}/fcm-tokens` após o switch; `DELETE` no logout.

## Sitemap web (após tenant)

```text
Turmas                    lista / criar / detalhe
  └─ Turma
       ├─ Matrículas
       ├─ Chamadas        lista → ao vivo / histórico da sessão
       └─ Relatório       frequência da turma → aluno
Salas                     lista / criar / editar
Equipe                    membros + convites          (admin)
```

## Sitemap mobile (após tenant)

```text
Início                    turmas do aluno (matrículas)
  └─ Turma                próxima/aberta chamada → Confirmar
Histórico                 sessões / status por turma
Conta                     instituição, sair
```

## Núcleo do produto (desenhar primeiro)

1. Web — Chamada ao vivo (código do dia + lista de records)
2. Mobile — Confirmar presença (código + GPS)
3. Web — Relatório de frequência
4. Web — Turmas e salas (cadastro que alimenta a chamada)
