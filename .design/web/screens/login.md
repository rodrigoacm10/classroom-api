# Login (web)

**Quem:** qualquer um. **Objetivo:** entrar no painel.

## Regiões

- Centro: logo + título “Entrar” + form (e-mail, senha) + primary “Entrar”
- Links: “Criar conta”, “Esqueci a senha”

## Dados

- Submit: `POST /auth/login` com `client_type: "web"` (cookie HttpOnly; UI não mostra token)
- Campos: `email`, `password`
- Schema: `src/modules/auth/interface/router.py` (`LoginRequest`)

Sucesso → escolha de instituição.

## Estados

- Loading no botão (disabled + “Entrando”)
- 401: “E-mail ou senha inválidos.” (rate limit 5/min — se 429, pedir espera)
- Vazio: botão disabled sem e-mail/senha

## Não mostrar

Tokens, `client_type`, cookie.
