# 🚀 Classroom API — Guia Rápido de Comandos

Guia direto com os comandos necessários para instalar dependências, executar a infraestrutura, a API, os trabalhadores Celery, migrações, testes e benchmarks.

---

## 📦 1. Instalar Dependências

```bash
uv sync
```

---

## 🐳 2. Subir Infraestrutura (PostgreSQL + Redis)

```bash
docker compose up -d
```

---

## 🗄️ 3. Rodar Migrações do Banco (Alembic)

```bash
uv run alembic upgrade head
```

---

## 🌐 4. Rodar a API (FastAPI / Uvicorn)

```bash
uv run uvicorn src.main:app --reload
```

---

## ⚙️ 5. Rodar o Celery Worker (Tarefas em Background / Push)

```bash
uv run celery -A src.infra.tasks.celery_app worker -l info
```

---

## ⏰ 6. Rodar o Celery Beat (Cronjob / Fechamento de Chamadas)

```bash
uv run celery -A src.infra.tasks.celery_app beat -l info
```

> **Dica (Worker + Beat juntos em 1 comando):**
> ```bash
> uv run celery -A src.infra.tasks.celery_app worker -B -l info
> ```

---

## ⚡ 7. Rodar o Benchmark de Paralelismo

```bash
uv run python scripts/benchmark_report.py --students 5000 --sessions 40 --intensity 40
```

---

## 🧪 8. Rodar os Testes Automatizados (Pytest)

```bash
uv run pytest
```
