FROM python:3.12-slim

# Dependências do sistema necessárias para psycopg, GeoAlchemy2 e Firebase
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libgeos-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala o uv
RUN pip install uv

WORKDIR /app

# Copia os arquivos de dependência primeiro (melhor uso de cache Docker)
COPY pyproject.toml uv.lock ./

# Instala dependências de produção (sem dev)
RUN uv sync --frozen --no-dev

# Copia o restante do código
COPY . .

# Porta padrão (Railway injeta $PORT automaticamente)
EXPOSE 8000

# Roda as migrations e sobe a API
CMD alembic upgrade head && uv run uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}
