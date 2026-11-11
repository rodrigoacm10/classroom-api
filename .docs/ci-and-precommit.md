# 🛡️ CI/CD & Automações de Qualidade de Código — Classroom API

Esta documentação descreve a infraestrutura de validação e publicação da **Classroom API**, em **três camadas**:

1. **Pre-commit Hook (Local)**: Impede a criação de commits que contenham violações de lint, formatação incorreta ou erros de tipagem estática.
2. **GitHub Actions CI (Remoto)**: Valida toda a base de código, formatação, tipos e executa os testes automatizados (com PostgreSQL e Redis reais) em cada `push` e `pull request`.
3. **CD na `main`**: Depois do CI verde, publica a imagem no GHCR e faz o Railway puxar aquele digest.

---

## 🏗️ As Duas Camadas de Proteção

```text
Desenvolvedor (Local)
       ↓
  git commit ───────────► Pre-commit Hook
                             ├── 1. Trailing whitespace / End of file
                             ├── 2. Ruff Linter (Auto-fix)
                             ├── 3. Ruff Formatter (Auto-format)
                             └── 4. Pyrefly (Type Check em src/)
                                    │
                                    ├── [FALHA]  ──► Bloqueia commit com mensagem explicativa
                                    └── [SUCESSO] ──► Grava o commit localmente
       ↓
  git push ────────────► GitHub Actions CI (.github/workflows/ci.yml)
                             ├── Job 1: Lint & Type Check (Ruff + Pyrefly)
                             └── Job 2: Test Suite (Unitários + Integração + E2E com Docker)
                                    │
                                    ├── [FALHA]  ──► Bloqueia merge no PR (❌)
                                    └── [SUCESSO] ──► Libera merge na branch dev/main (✅)
       ↓
  merge na main ────────► CD (.github/workflows/cd.yml), só se o CI passou
                             ├── docker build + push para ghcr.io
                             ├── anota tag sha-<commit> e digest sha256:...
                             └── Railway aponta o serviço para imagem@digest e faz pull
```

---

## 1. Pre-commit Hook Local (`.pre-commit-config.yaml`)

O arquivo [`.pre-commit-config.yaml`](file:///home/rodrigo/projects/classroom/classroom-api/.pre-commit-config.yaml) orquestra os hooks executados pelo Git antes de qualquer commit ser persistido.

### Hooks Configurados:

* **Higiene básica**: Remoção de espaços em branco ao final das linhas (`trailing-whitespace`), garantia de quebra de linha no final do arquivo (`end-of-file-fixer`), sintaxe de arquivos YAML (`check-yaml`) e bloqueio de arquivos binários acidentais (`check-added-large-files`).
* **Linter (Ruff)**: Roda `uv run ruff check --fix` corrigindo automaticamente problemas de importação (`isort`), variáveis sem uso e más práticas.
* **Formatador (Ruff)**: Roda `uv run ruff format` padronizando a indentação e largura de linha (100 colunas).
* **Verificador de Tipos (Pyrefly)**: Roda `uv run pyrefly check src` garantindo que nenhuma alteração quebre contratos de tipos estáticos.

### Instalação e Ativação dos Hooks

Após clonar o repositório ou instalar as dependências, os hooks do git são ativados com:

```bash
uv run pre-commit install
```

### Executar Manualmente

Você pode rodar os hooks a qualquer momento sem precisar fazer um commit:

```bash
# Rodar apenas nos arquivos modificados (staged)
uv run pre-commit run

# Rodar em todo o repositório
uv run pre-commit run --all-files
```

---

## 2. GitHub Actions CI (`.github/workflows/ci.yml`)

O workflow [`.github/workflows/ci.yml`](file:///home/rodrigo/projects/classroom/classroom-api/.github/workflows/ci.yml) é disparado a cada `push` e `pull_request` nas branches `dev` e `main`.

Ele divide a execução em dois jobs paralelos:

### Job 1: `lint-and-typecheck` (Rápido: ~15 segundos)

* Configura Python 3.12 com cache `uv`.
* Roda:
  1. `uv run ruff check src` (valida regras de lint)
  2. `uv run pyrefly check src` (valida integridade de tipos com o Pyrefly)

### Job 2: `tests` (Completo: ~40 segundos)

* Sobe contêineres de serviço oficiais idênticos aos do `docker-compose`:
  * **PostgreSQL + PostGIS**: `postgis/postgis:16-3.4` (banco `classroom_test` pronto para receber extensões espaciais).
  * **Redis**: `redis:7-alpine`.
* Roda toda a suíte de testes:
  ```bash
  uv run pytest
  ```

  Isso executa todos os testes **Unitários**, de **Integração** e **E2E** (end-to-end com endpoints HTTP reais).

---

## 3. CD — GHCR + digest + Railway (`.github/workflows/cd.yml`)

O job `publish-and-deploy` do CI chama esse workflow **somente** em `push` na `main`, e **somente** se `Lint & Type Check` e `Test Suite (Unit, Integration & E2E)` passaram. Pull request não publica imagem.

O que o CD faz:

1. Recusa seguir se faltarem `RAILWAY_API_TOKEN`, `RAILWAY_PROJECT_ID`, `RAILWAY_ENVIRONMENT_ID` ou `RAILWAY_SERVICE`.
2. Constrói a imagem `linux/amd64` com o `Dockerfile` e envia ao GHCR.
3. Publica a tag imutável na prática `sha-<commit>` (o commit SHA não se repete).
4. Escreve no log e no summary a referência fixa `ghcr.io/<owner>/classroom-api@sha256:...`.
5. Troca a source de cada serviço Railway para **esse digest** (`railway service source connect --image`). Isso desconecta o deploy por Git: o Railway deixa de buildar o repositório.
6. Dispara um deploy novo com `railway redeploy --from-source`. Sem `--from-source`, o CLI repetiria o container antigo e ignoraria o digest recém-gravado.

`RAILWAY_EXTRA_SERVICES` é opcional: nomes separados por vírgula (worker, beat) que devem subir **a mesma imagem**. A migration fica só no serviço da API.

### Por que a migration saiu do `CMD`

O `CMD` da imagem só sobe o Uvicorn. A migration é o **Pre-deploy Command** do serviço da API no Railway:

```text
uv run alembic upgrade head
```

Esse comando roda num container efêmero, com as variáveis do serviço, **antes** do processo novo assumir o tráfego. Se o Alembic falha, o deploy para e a versão anterior continua no ar. Um worker que usa a mesma imagem não executa migration, porque o pre-deploy é configuração daquele serviço, não da imagem.

### O que você configura uma vez (fora do Git)

Branch protection, secrets e o painel do Railway não ficam no repositório.

1. No serviço da API, em Settings → Deploy, Pre-deploy Command: `uv run alembic upgrade head`. Deixe o Custom Start Command vazio para valer o `CMD` da imagem. Se existir worker ou beat, o start command deles continua o comando do Celery, **sem** pre-deploy.
2. Crie um account token e salve os secrets da tabela abaixo. Desconecte o repositório Git da source do serviço **antes** do merge deste fluxo, para o Railway parar de buildar o código. O container que já está no ar continua até o CD trocar a source.
3. No GitHub, em Settings → Branches → rule da `main`: exija pull request e estes status checks: `Lint & Type Check` e `Test Suite (Unit, Integration & E2E)`.

Não marque `Publish image and deploy` como obrigatório. Em pull request esse job é ignorado, e um check obrigatório ignorado impede o merge.

Imagem privada no GHCR exige Railway Pro para o pull. No Hobby, a alternativa é tornar o pacote público em GitHub → Packages. Aí qualquer pessoa consegue baixar a imagem, mesmo com o repositório privado.

### Secrets do repositório

| Secret | Valor |
| --- | --- |
| `RAILWAY_API_TOKEN` | Account token, criado em railway.com/account/tokens com "No workspace" |
| `RAILWAY_PROJECT_ID` | ID do projeto, variável `RAILWAY_PROJECT_ID` do serviço |
| `RAILWAY_ENVIRONMENT_ID` | ID do ambiente de produção, variável `RAILWAY_ENVIRONMENT_ID` do serviço |
| `RAILWAY_SERVICE` | Nome do serviço da API no Railway |
| `RAILWAY_EXTRA_SERVICES` | Opcional. Outros serviços da mesma imagem, separados por vírgula |

`RAILWAY_TOKEN` é project token. O CLI recusa com ele o comando que troca a imagem do serviço. O workflow não usa mais esse secret.

---

## ⚙️ Configurações no `pyproject.toml`

As ferramentas de qualidade compartilham suas configurações diretamente no [`pyproject.toml`](file:///home/rodrigo/projects/classroom/classroom-api/pyproject.toml):

```toml
[tool.pyrefly]
search_path = ["src", "."]

[tool.ruff]
line-length = 100
target-version = "py312"
exclude = [
    ".venv",
    ".git",
    "alembic",
    "__pycache__",
]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes (unbound variables, imports não utilizados)
    "I",   # isort (ordenação e agrupamento automático de imports)
]
ignore = [
    "E501",  # largura de linha delegada ao ruff format
]

[tool.ruff.lint.per-file-ignores]
"src/infra/tasks/celery_app.py" = ["E402"]
"tests/**" = ["E402", "F841"]

[tool.ruff.lint.isort]
known-first-party = ["config", "infra", "modules", "security", "shared", "tests"]
```
