# Guia de desenvolvimento — Classroom API

Este documento descreve como rodar o projeto do zero, o fluxo do dia a dia e o processo completo de migrations com Alembic.

---

## Cola rápida — dia a dia

Abra o projeto e use **dois terminais**.

### Terminal 1 — Infraestrutura (Postgres + Redis)

```bash
cd classroom-api
docker compose up -d
docker compose ps          # confirmar status "healthy"
```

Para parar ao final do dia:

```bash
docker compose down
```

### Terminal 2 — API Python

Ative o ambiente virtual e suba a API:

```bash
cd classroom-api
source .venv/bin/activate
uvicorn main:app --reload --app-dir src
```

Alternativa sem ativar o `.venv` (o `uv` cuida do ambiente):

```bash
cd classroom-api
uv run uvicorn main:app --reload --app-dir src
```

Acesse:

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs

### Com `.venv` ativado — outros comandos úteis

```bash
source .venv/bin/activate   # se ainda não ativou neste terminal

pytest                      # rodar testes
pytest -v                   # testes com detalhe

alembic revision --autogenerate -m "descricao"   # gerar migration
alembic upgrade head                             # aplicar migrations
alembic current                                  # ver revision atual
alembic history                                # listar migrations
```

### Com `uv run` (sem ativar `.venv`)

```bash
uv run pytest
uv run alembic revision --autogenerate -m "descricao"
uv run alembic upgrade head
uv run alembic current
```

### Encerrar o dia

```bash
# Terminal 2: Ctrl+C para parar a API
deactivate                  # opcional — sai do .venv

# Terminal 1:
docker compose down
```

### Resumo em sequência

```bash
# 1) Infra
cd classroom-api && docker compose up -d

# 2) API
cd classroom-api && source .venv/bin/activate
uvicorn main:app --reload --app-dir src

# 3) Migration (quando alterar models)
alembic revision --autogenerate -m "descricao"
# revisar alembic/versions/...
alembic upgrade head
```

> Se o `.venv` ainda não existir, rode `uv sync` uma vez antes de `source .venv/bin/activate`.

---

Instale uma vez na máquina:

| Ferramenta | Para quê | Verificar |
|---|---|---|
| Python 3.12+ | Runtime | `python3 --version` |
| [uv](https://docs.astral.sh/uv/) | Dependências e ambiente | `uv --version` |
| Docker + Docker Compose | Postgres/PostGIS e Redis | `docker --version` e `docker compose version` |

Os containers **não sobem automaticamente** ao ligar o PC (`restart: "no"` no `docker-compose.yml`). Eles só rodam quando você executar `docker compose up -d`.

---

## Setup do zero

Siga na ordem na primeira vez (ou ao clonar o repositório em outra máquina).

### 1. Clonar e entrar no projeto

```bash
git clone <url-do-repositorio> classroom-api
cd classroom-api
```

### 2. Instalar dependências Python

```bash
uv sync
```

Cria/atualiza o `.venv` e instala tudo que está no `pyproject.toml` e no `uv.lock`.

### 3. Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Edite o `.env` se necessário. Em dev local, os valores padrão já batem com o `docker-compose.yml`.

| Variável | Uso |
|---|---|
| `DATABASE_URL` | Conexão Postgres (SQLAlchemy + Alembic) |
| `REDIS_URL` | Redis (Celery/cache, quando usar) |
| `JWT_SECRET` | Assinatura de tokens JWT |

> O arquivo `.env` **não vai para o git**. Nunca commite secrets.

### 4. Subir a infraestrutura (Docker)

```bash
docker compose up -d
```

Confirme que os containers estão saudáveis:

```bash
docker compose ps
```

Esperado: `classroom-postgres` e `classroom-redis` com status **healthy**.

### 5. Rodar a API

```bash
source .venv/bin/activate
uvicorn main:app --reload --app-dir src
```

Ou:

```bash
uv run uvicorn main:app --reload --app-dir src
```

Acesse:

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs

### 6. (Opcional) Rodar testes

```bash
uv run pytest
```

---

## Dia a dia — fluxo normal

> Comandos resumidos no topo: [Cola rápida — dia a dia](#cola-rápida--dia-a-dia).

Use **dois terminais** (ou rode infra em background).

### Terminal 1 — Infraestrutura

```bash
cd classroom-api
docker compose up -d
docker compose ps
```

Para parar quando terminar de trabalhar:

```bash
docker compose down
```

| Comando | O que faz |
|---|---|
| `docker compose up -d` | Sobe Postgres + Redis em background |
| `docker compose ps` | Mostra status dos containers |
| `docker compose down` | Para os containers (dados persistem nos volumes) |
| `docker compose down -v` | Para **e apaga** os dados (reset total do banco) |

### Terminal 2 — API

Com `.venv` ativado:

```bash
cd classroom-api
source .venv/bin/activate
uvicorn main:app --reload --app-dir src
```

Ou com `uv run` (sem ativar o `.venv`):

```bash
cd classroom-api
uv run uvicorn main:app --reload --app-dir src
```

O `--reload` reinicia a API automaticamente quando você salva arquivos `.py`.

### Resumo visual

```text
┌─────────────────────────────────────────────────────────┐
│  Terminal 1                                             │
│  docker compose up -d    →  Postgres + Redis              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Terminal 2                                             │
│  uv run uvicorn main:app --reload --app-dir src         │
│                         →  FastAPI em :8000             │
└─────────────────────────────────────────────────────────┘
```

---

## Estrutura relevante

```text
classroom-api/
├── .env                    # config local (não commitado)
├── .env.example            # template de config
├── docker-compose.yml      # Postgres/PostGIS + Redis
├── alembic/                # migrations
│   ├── env.py
│   └── versions/           # arquivos de migration
├── src/
│   ├── main.py             # entrada FastAPI
│   ├── config/settings.py  # lê o .env
│   └── infra/db/
│       ├── base.py         # Base dos models SQLAlchemy
│       ├── session.py      # engine + get_db()
│       └── models/         # models do banco
└── tests/
```

---

## Migrations — processo completo

### Conceitos rápidos

| Peça | Papel |
|---|---|
| **SQLAlchemy models** (`src/infra/db/models/`) | Definem tabelas no código Python |
| **Alembic** (`alembic/versions/`) | Gera e aplica SQL no Postgres |
| **`Base.metadata`** | Registro de todas as tabelas — usado pelo `--autogenerate` |

Fluxo:

```text
Model Python  →  alembic revision --autogenerate  →  arquivo em versions/
                                                          ↓
                                              alembic upgrade head
                                                          ↓
                                                   tabela no Postgres
```

### Pré-requisito

Postgres rodando:

```bash
docker compose up -d
```

---

### Passo 1 — Criar o model

Exemplo em `src/infra/db/models/user.py`:

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from infra.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
```

### Passo 2 — Registrar o model para o Alembic

Em `src/infra/db/models/__init__.py`, importe o model:

```python
from infra.db.models.user import User
```

Sem esse import, o `--autogenerate` **não vê** a tabela.

### Passo 3 — Gerar a migration

```bash
uv run alembic revision --autogenerate -m "create users table"
```

Isso cria um arquivo em `alembic/versions/`, por exemplo:

```text
alembic/versions/a1b2c3d4_create_users_table.py
```

### Passo 4 — Revisar o arquivo gerado

**Sempre leia** o arquivo antes de aplicar. O autogenerate pode:

- esquecer detalhes (índices, constraints)
- incluir mudanças indesejadas

Abra o `.py` em `alembic/versions/` e confira as funções `upgrade()` e `downgrade()`.

### Passo 5 — Aplicar no banco

```bash
uv run alembic upgrade head
```

`head` = última migration disponível.

### Passo 6 — Confirmar

```bash
uv run alembic current
```

Mostra a revision aplicada no banco.

---

## Comandos Alembic — referência

| Comando | O que faz |
|---|---|
| `uv run alembic revision --autogenerate -m "descricao"` | Gera migration a partir dos models |
| `uv run alembic revision -m "descricao"` | Cria migration vazia (manual) |
| `uv run alembic upgrade head` | Aplica todas as migrations pendentes |
| `uv run alembic downgrade -1` | Desfaz a última migration |
| `uv run alembic current` | Mostra revision atual no banco |
| `uv run alembic history` | Lista todas as migrations |
| `uv run alembic upgrade +1` | Aplica só a próxima migration |
| `uv run alembic downgrade base` | Remove todas as migrations (cuidado!) |

---

## Alterar um model existente

1. Edite o model em `src/infra/db/models/`
2. Gere nova migration:

   ```bash
   uv run alembic revision --autogenerate -m "add phone to users"
   ```

3. Revise o arquivo gerado
4. Aplique:

   ```bash
   uv run alembic upgrade head
   ```

---

## Testes

```bash
uv run pytest
```

Com mais detalhe:

```bash
uv run pytest -v
uv run pytest tests/test_health.py
```

---

## Comandos úteis do dia a dia

```bash
# Dependências
uv sync                          # instala/atualiza deps
uv add <pacote>                  # adiciona dependência
uv add --dev <pacote>            # dependência de dev

# API
uv run uvicorn main:app --reload --app-dir src

# Infra
docker compose up -d
docker compose down

# Migrations
uv run alembic revision --autogenerate -m "descricao"
uv run alembic upgrade head

# Testes
uv run pytest
```

---

## Troubleshooting

### `Connection refused` ao rodar migration ou API

Postgres provavelmente não está rodando:

```bash
docker compose up -d
docker compose ps
```

### Alembic não detecta tabelas no `--autogenerate`

- Confirme que o model herda de `Base`
- Confirme o import em `src/infra/db/models/__init__.py`

### Porta 5432 ou 6379 já em uso

Outro Postgres/Redis pode estar rodando na máquina. Pare o serviço conflitante ou altere as portas no `docker-compose.yml`.

### Mudou o `.env` e a API não reflete

Reinicie o Uvicorn (Ctrl+C e suba de novo). Com `--reload`, mudanças em `.py` recarregam; mudanças no `.env` podem exigir restart manual.

### Reset completo do banco local

```bash
docker compose down -v
docker compose up -d
uv run alembic upgrade head
```

Apaga volumes e recria tudo do zero.

---

## Checklist rápido

**Primeira vez:**

- [ ] `uv sync`
- [ ] `cp .env.example .env`
- [ ] `docker compose up -d`
- [ ] `uv run uvicorn main:app --reload --app-dir src`
- [ ] Abrir http://localhost:8000/docs

**Nova migration:**

- [ ] Model criado em `src/infra/db/models/`
- [ ] Import em `src/infra/db/models/__init__.py`
- [ ] `docker compose up -d`
- [ ] `uv run alembic revision --autogenerate -m "..."`
- [ ] Revisar arquivo em `alembic/versions/`
- [ ] `uv run alembic upgrade head`
