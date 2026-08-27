Aqui está a explicação sobre o Docker e o **Guia Definitivo Atualizado**:

---

## Como o Banco de Testes funciona no Docker?

O seu `docker-compose.yml` sobe um container chamado `classroom-postgres`.

Quando criamos o banco `classroom_test` com o comando:

```bash
docker exec classroom-postgres createdb -U classroom classroom_test
```

Nós criamos um **segundo banco de dados dentro do mesmo container** do PostgreSQL que já está rodando na sua máquina.

### Resposta à sua dúvida:

- **Sim! Ele sobe automaticamente com o `docker compose up -d`.**
- Como o Docker guarda os dados num volume (`postgres_data`), o banco `classroom_test` **já fica salvo permanentemente**.
- Mesmo se você reiniciar o computador ou dar `docker compose stop` / `docker compose up -d`, o `classroom_test` continua lá pronto para uso!
- _(Você só precisará recriá-lo se um dia rodar `docker compose down -v`, que apaga os volumes do Docker)._

---

## 🚀 Guia Definitivo de Execução de Testes

### 1. Pré-requisito (Infraestrutura)

Para rodar testes de **Integração** ou **Tudo junto**, o container do banco de dados precisa estar rodando:

```bash
# 1. Subir os containers do projeto (se já não estiverem rodando)
docker compose up -d

# 2. (Garantia/Primeira vez apenas) Criar o banco de testes se não existir:
docker exec classroom-postgres createdb -U classroom classroom_test 2>/dev/null || true
```

---

### 2. Rodar Apenas Testes Unitários

> **Não precisa do Docker rodando!** Roda 100% em memória RAM em milissegundos.

```bash
uv run pytest tests/unit/ -v
```

---

### 3. Rodar Apenas Testes de Integração

> **Requer o Docker rodando!** Testa os repositórios SQLAlchemy no banco `classroom_test` real.

```bash
uv run pytest tests/integration/ -v
```

---

### 4. Rodar Apenas Testes E2E (End-to-End)

> **Requer o Docker rodando!** Dispara requisições HTTP reais aos endpoints FastAPI contra o PostgreSQL de testes e o Redis.

```bash
uv run pytest tests/e2e/ -v
```

---

### 5. Rodar a Suíte Completa (Tudo Junto)

> **Requer o Docker rodando!** Roda Unitários + Integração + E2E em sequência.

```bash
uv run pytest tests/ -v
```

---

### 🛠️ Comandos de Atalho para o Dia a Dia

```bash
# Rodar apenas um arquivo específico (ex: E2E do módulo auth):
uv run pytest tests/e2e/modules/auth/test_auth_router.py -v

# Rodar apenas um teste específico pelo nome:
uv run pytest -k "test_find_by_email" -v

# Parar no primeiro erro que encontrar (flag -x):
uv run pytest tests/ -x -v
```

