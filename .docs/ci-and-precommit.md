# 🛡️ CI/CD & Automações de Qualidade de Código — Classroom API

Esta documentação descreve a infraestrutura de validação estática e testes automatizados configurada na **Classroom API**, dividida em **duas camadas**:

1. **Pre-commit Hook (Local)**: Impede a criação de commits que contenham violações de lint, formatação incorreta ou erros de tipagem estática.
2. **GitHub Actions CI (Remoto)**: Valida toda a base de código, formatação, tipos e executa os testes automatizados (com PostgreSQL e Redis reais) em cada `push` e `pull request`.

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
