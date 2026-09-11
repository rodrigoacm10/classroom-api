# Instituição (web)

**Quem:** usuário logado. **Objetivo:** escolher a tenant do JWT.

## Regiões

- Lista de cards: `name`, `role`
- Vazio: “Você ainda não participa de uma instituição.” + texto sobre convite por e-mail
- Sem primary global (a ação é o card)

## Dados

- Lista: `GET /tenants/me` → `name`, `slug`, `role`, `active`
- Entrar: `POST /auth/switch-tenant` `{ tenant_id }`
- Schema: `src/modules/tenant/interface/schemas/tenant_schemas.py` (`MyTenantResponse`)

## Estados

- Loading da lista
- Tenant `active = false`: não clicável, indicar “Inativa”
- Erro 403 no switch: “Sem acesso a esta instituição.”

## Não mostrar

`id` cru, `deleted`, `created_at`.
