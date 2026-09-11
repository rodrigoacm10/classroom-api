# Login (mobile)

**Quem:** aluno. **Objetivo:** entrar no app.

## Regiões

- Marca no topo
- E-mail, senha, primary full-width “Entrar”
- “Criar conta”, “Esqueci a senha”

## Dados

- `POST /auth/login` com `client_type: "mobile"` — `access_token` e `refresh_token` no body (o app guarda; a UI não exibe)
- Schema: `LoginRequest` / `LoginMobileResponse` em `auth/interface/router.py`

## Estados

Iguais ao web: 401, 429, loading no botão.

## Não mostrar

Tokens.
