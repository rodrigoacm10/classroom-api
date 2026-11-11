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

# Só sobe a API. A migration NÃO roda aqui.
# No Railway ela é o Pre-deploy Command do serviço da API:
#   uv run alembic upgrade head
# Assim um worker que usa esta mesma imagem não altera o banco,
# e um erro de migration cancela o deploy antes do processo novo subir.
# /bin/sh -c existe para expandir $PORT.
CMD ["/bin/sh", "-c", "uv run uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
