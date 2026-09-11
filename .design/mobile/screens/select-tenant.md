# Instituição (mobile)

**Quem:** usuário logado. **Objetivo:** escolher tenant (igual ao web, lista full-screen).

## Dados

- `GET /tenants/me` → `name`, `role`, `active`
- `POST /auth/switch-tenant` `{ tenant_id }`
- Em seguida, registrar push: `POST /tenants/{tenant_id}/fcm-tokens` (sem UI)

Tenant inativa: não entra.
