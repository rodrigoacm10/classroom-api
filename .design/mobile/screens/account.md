# Conta (mobile)

**Quem:** autenticado. **Objetivo:** ver instituição atual e sair.

## Regiões

- `name` da tenant + `role`
- Trocar instituição (volta ao fluxo `GET /tenants/me`)
- Sair: `POST /auth/logout` + `DELETE /tenants/{id}/fcm-tokens/{device_id}`

Sem tela de “editar perfil” (não há `PATCH /users` na API).
