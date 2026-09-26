# 🛠️ Comandos Rápidos de Execução — Classroom API

## 1. Instalar Dependências
```bash
uv sync
```

## 2. Subir Banco de Dados e Redis (Docker)
```bash
docker compose up -d
```

## 3. Rodar Migrações (Alembic)
```bash
uv run alembic upgrade head
```

## 4. Rodar a API (FastAPI)
```bash
uv run uvicorn src.main:app --reload
```

## 5. Rodar o Celery Worker (Background Tasks / Push)
```bash
uv run celery -A src.infra.tasks.celery_app worker -l info
```

## 6. Rodar o Celery Beat (Cronjob de Chamadas Expiradas)
```bash
uv run celery -A src.infra.tasks.celery_app beat -l info
```

> **Worker + Beat no mesmo processo (simplificado):**
> ```bash
> uv run celery -A src.infra.tasks.celery_app worker -B -l info
> ```

## 7. Rodar o Benchmark de Paralelismo
```bash
uv run python scripts/benchmark_report.py --students 5000 --sessions 40 --intensity 40
```

## 8. Rodar a Suíte de Testes (Pytest)
```bash
uv run pytest
```
