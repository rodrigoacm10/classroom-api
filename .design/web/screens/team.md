# Equipe (web)

**Quem:** admin. **Objetivo:** convites e papéis.

## Regiões

- Form convite: `email` + `role` + “Enviar convite”
- Lista de convites pendentes: e-mail, papel, `expires_at`, revogar
- Lista de membros: papel, alterar role, remover (não o último admin)

## Dados

- Enviar: `POST /tenants/{tenant_id}/invites` `{ email, role }`
- Revogar: `DELETE /tenants/{tenant_id}/invites/{invite_id}`
- Papel: `PATCH /tenants/{tenant_id}/members/{user_id}/role`
- Remover: `DELETE /tenants/{tenant_id}/members/{user_id}`
- Schema: `tenant_schemas.py` (`InviteStatusResponse`, `TenantMemberResponse`)

Não há `GET` de membros/convites na API ainda. No Paper, desenhar as duas listas; marcar no artboard “lista depende de endpoint futuro” se for o caso. Preferir não inventar campos.

## Não mostrar

`token` do convite na tabela (o aceite é pelo link do e-mail).
