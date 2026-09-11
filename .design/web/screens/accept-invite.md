# Aceite de convite (web)

**Quem:** convidado (link do e-mail). **Objetivo:** ver o convite e entrar na instituição.

Fora do shell. Card central.

## Regiões

- `tenant_name`, `role`, `email`, validade (`expires_at`)
- Se não logado: “Entrar” / “Criar conta” e voltar para esta URL
- Se logado: primary “Aceitar convite”

## Dados

- `GET /invites/{token}` → status `pending | accepted | expired | revoked`
- `POST /invites/{token}/accept` (auth; e-mail tem que bater)
- Schema: `InviteStatusResponse`

## Estados

- pending: CTA aceite
- expired / revoked / accepted: mensagem, sem botão
- 403: “Este convite não é para esta conta.”

## Não mostrar

`token` como texto copiável na UI (já está na URL).
