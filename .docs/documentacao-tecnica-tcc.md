# Documentação Técnica — Sistema de Chamada Acadêmica com Validação por Geolocalização

## Guia de Arquitetura e Desenvolvimento

---

## 1. Visão geral da arquitetura

### 1.1 Diagrama de infraestrutura

```
┌─────────────────────┐         ┌─────────────────────┐
│   App Mobile         │         │   Painel Web          │
│   (React Native)      │         │   (React)             │
│   - Aluno              │         │   - Professor/Admin    │
└──────────┬───────────┘         └──────────┬───────────┘
           │                                 │
           │           HTTPS / REST JSON     │
           └────────────────┬────────────────┘
                             │
                    ┌────────▼─────────┐
                    │   API Backend      │
                    │   FastAPI (Python) │
                    └────────┬─────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                     │
┌───────▼────────┐  ┌────────▼─────────┐  ┌────────▼────────┐
│ PostgreSQL       │  │ Redis (broker)    │  │ Storage (S3/MinIO)│
│ + PostGIS         │  │ + Celery workers   │  │ (fotos evidência)  │
│ (Neon)            │  │ (tarefas async)     │  │                    │
└───────────────────┘  └─────────────────────┘  └────────────────────┘
                             │
                    ┌────────▼─────────┐
                    │  Serviços externos │
                    │  FCM (push)         │
                    │  Resend/SES (email)  │
                    └───────────────────┘
```

**Princípio de design**: a API é o único ponto de entrada. App mobile e painel web nunca acessam banco, storage ou filas diretamente — tudo passa pela API REST, que aplica autenticação, autorização e regras de negócio.

---

### 1.2 Padrão arquitetural — Clean Architecture

O backend segue **Clean Architecture** com **Ports & Adapters**, organizado por módulos de domínio. As dependências apontam **sempre para dentro**:

```
interface → application → domain ← (nunca para fora)
                              ↑
                            infra
```

| Camada | Responsabilidade |
|---|---|
| `domain/` | Entidades, regras de negócio puras, interfaces de repositório. Não conhece FastAPI, SQLAlchemy, Redis nem HTTP. |
| `application/` | Casos de uso: orquestra o domínio, chama repositórios via interface, não conhece HTTP nem SQLAlchemy. |
| `infra/` | Implementações concretas: SQLAlchemy, Celery, FCM, S3/MinIO, Redis. Implementa as interfaces definidas no domínio. |
| `interface/` | Camada HTTP: routers FastAPI + schemas Pydantic. Recebe a requisição, delega ao caso de uso, devolve a resposta. |

#### Ciclo de vida de uma requisição

```
HTTP Request
      ↓
Middleware
      ↓
Autenticação (Depends)
      ↓
Autorização por papel (Depends)
      ↓
FastAPI Router  ←── schema Pydantic valida entrada
      ↓
Use Case        ←── recebe dados simples, sem HTTP
      ↓
Domain Service  ←── regras de negócio puras
      ↓
Repository Interface (Protocol)
      ↑
SQLAlchemy Repository
      ↓
PostgreSQL
      ↓
Mapper  →  Response Schema  →  HTTP Response
```

Para operações assíncronas pesadas (notificações em lote, relatórios):

```
HTTP Request
      ↓
Use Case
      ↓
Celery Task → Redis → Worker → FCM / Resend / S3
```

#### Fluxo de dependências

```
                    ┌─────────────────────┐
                    │   FastAPI Interface  │
                    │   (router + schemas) │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Application      │
                    │    Use Cases        │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │       Domain        │
                    │ Entidades / Serviços │
                    │  Repository Ports   │
                    └──────────┬──────────┘
                               ▲
                               │ implementa
                    ┌──────────┴──────────┐
                    │   Infrastructure    │
                    │    SQLAlchemy       │
                    │  Redis / Celery     │
                    │  FCM / S3 / e-mail  │
                    └─────────────────────┘
```

#### Regras invioláveis

1. **`domain/` não importa** FastAPI, SQLAlchemy, Pydantic, Redis nem Celery.
2. **Casos de uso não acessam** `session` do SQLAlchemy diretamente — sempre via interface de repositório.
3. **Routers são finos** — recebem a requisição, chamam o caso de uso, devolvem a resposta. Sem lógica de negócio.
4. **Operações pesadas usam Celery** — e-mails, notificações em lote, relatórios não bloqueiam o request.
5. **Variáveis de ambiente** são lidas apenas em `config/settings.py`; o restante recebe configuração via injeção de dependência.
6. **Entidades de domínio nunca são retornadas diretamente pela HTTP** — passam pelo mapper e pelo schema de resposta.

---

## 2. Ferramentas e por que cada uma foi escolhida

| Camada | Ferramenta | Papel no sistema |
|---|---|---|
| App mobile | **React Native** | Interface do aluno: recebe notificação, escaneia/digita código, envia geolocalização e evidência |
| Painel web | **React** | Interface do professor/admin: abre chamada, gera código, acompanha presença em tempo real, gera relatórios |
| Backend | **FastAPI (Python)** | Expõe a API REST, aplica regras de negócio, orquestra banco/fila/storage |
| Banco de dados | **PostgreSQL + PostGIS (Neon)** | Armazena dados relacionais + calcula distância geoespacial com precisão e índice otimizado |
| ORM | **SQLAlchemy + GeoAlchemy2** | Mapeamento objeto-relacional, incluindo tipos geográficos |
| Fila assíncrona | **Celery + Redis** (evolução de `BackgroundTasks`) | Processa notificações em lote e relatórios sem travar a API |
| Notificação push | **Firebase Cloud Messaging (FCM)** | Avisa o aluno em tempo real quando a chamada abre |
| E-mail | **Resend / SendGrid / SES** | Confirmações, relatórios periódicos, alertas formais |
| Armazenamento de arquivos | **MinIO ou AWS S3** | Guarda fotos de evidência fora do banco relacional |
| Autenticação | **JWT (JSON Web Token)** | Autentica requisições da API sem manter sessão no servidor |
| Versionamento | **Git + GitHub** | Histórico de código, colaboração em equipe, obrigatório pela disciplina |
| Testes | **Pytest** (backend) + **Jest** (frontend/mobile) | Garantir que regras de negócio críticas (ex: validação de presença) não quebrem |
| Contêineres | **Docker + Docker Compose** | Padronizar ambiente de desenvolvimento entre os integrantes da equipe |

---

## 3. Modelagem do banco de dados

### 3.1 Entidades principais

```
users
├── id (PK)
├── name
├── email (unique)
├── password_hash
├── role (enum: admin, professor, aluno, coordenador)
├── fcm_token          -- token do dispositivo para push notification
├── created_at

classes (turmas)
├── id (PK)
├── name
├── discipline_name
├── professor_id (FK -> users.id)
├── created_at

class_students (relação N:N entre turma e aluno)
├── id (PK)
├── class_id (FK -> classes.id)
├── student_id (FK -> users.id)

rooms (salas)
├── id (PK)
├── name
├── location (GEOGRAPHY(Point, 4326))   -- coluna PostGIS
├── tolerance_radius_meters
├── created_by (FK -> users.id)

attendance_sessions (janela de chamada aberta)
├── id (PK)
├── class_id (FK -> classes.id)
├── room_id (FK -> rooms.id)
├── day_code (código do dia, gerado)
├── opened_at
├── expires_at
├── status (enum: open, closed)

attendance_records (confirmação individual de presença)
├── id (PK)
├── session_id (FK -> attendance_sessions.id)
├── student_id (FK -> users.id)
├── confirmed_at
├── student_location (GEOGRAPHY(Point, 4326))
├── distance_meters      -- calculado no momento da confirmação
├── within_radius (boolean)
├── evidence_photo_url (nullable)
├── UNIQUE(session_id, student_id)   -- impede duplicidade

notifications_log
├── id (PK)
├── session_id (FK -> attendance_sessions.id)
├── student_id (FK -> users.id)
├── sent_at
├── status (enum: sent, failed)
```

### 3.2 Pontos de atenção na modelagem
- A constraint `UNIQUE(session_id, student_id)` em `attendance_records` é a primeira linha de defesa contra duplicidade — mas **não resolve** race condition sozinha (ver seção de concorrência abaixo).
- `location` e `student_location` usam o tipo `GEOGRAPHY(Point, 4326)` do PostGIS — o `4326` é o SRID (sistema de referência), padrão para coordenadas GPS (latitude/longitude, WGS84).
- Criar índice espacial GiST na coluna `location` de `rooms` para consultas geoespaciais eficientes:
```sql
CREATE INDEX idx_rooms_location ON rooms USING GIST(location);
```

---

## 4. Fluxo principal do sistema (passo a passo técnico)

### 4.1 Abertura da chamada (professor)
1. Professor autentica (`POST /auth/login`) → recebe JWT
2. `POST /classes/{id}/attendance-sessions` → cria registro em `attendance_sessions`, gera `day_code` aleatório, define `expires_at`
3. Backend dispara tarefa assíncrona (Celery) para notificar todos os alunos da turma via FCM
4. Retorna `session_id` para o painel do professor, que passa a fazer polling ou usar WebSocket para acompanhar confirmações em tempo real

### 4.2 Confirmação de presença (aluno)
1. Aluno recebe push notification → abre o app
2. Digita/escaneia `day_code`
3. App captura geolocalização (GPS) do dispositivo
4. (Opcional) App captura foto de evidência
5. `POST /attendance-sessions/{id}/confirm` com `day_code`, `latitude`, `longitude`, `photo` (opcional)
6. Backend valida, nesta ordem:
   - Sessão ainda está `open` e dentro do prazo (`expires_at`)
   - `day_code` confere
   - Calcula distância via PostGIS: `ST_DWithin(room.location, student_location, tolerance_radius_meters)`
   - Insere em `attendance_records` dentro de uma transação com tratamento de concorrência (ver seção 5)
7. Retorna sucesso/falha com o motivo (ex: "fora do raio permitido", "código expirado")

### 4.3 Fechamento e relatório
1. Sessão expira automaticamente (`expires_at` alcançado) ou professor encerra manualmente
2. Job assíncrono processa relatório de frequência (pode ser paralelizado por turma/aluno)
3. Relatório fica disponível para consulta e pode ser enviado por e-mail periodicamente

---

## 5. Como tratar a concorrência (o núcleo técnico do projeto)

Esse é o ponto que sustenta o componente de "otimização de processamento" da disciplina de Tópicos Avançados. Precisa ser implementado com cuidado e, idealmente, **testado e documentado com números**.

### 5.1 O problema
Quando a chamada abre, dezenas de alunos podem enviar `POST /attendance-sessions/{id}/confirm` em um intervalo de poucos segundos. Sem controle adequado:
- Duas requisições do mesmo aluno podem ser processadas ao mesmo tempo, gerando inconsistência
- Sob alta carga, o banco pode sofrer contenção de locks, aumentando o tempo de resposta

### 5.2 Estratégias possíveis (escolher e justificar uma)

**Opção A — Constraint UNIQUE + tratamento de erro (mais simples)**
A constraint `UNIQUE(session_id, student_id)` faz o banco rejeitar duplicatas automaticamente. O backend captura a exceção de violação de constraint e retorna "presença já confirmada" de forma amigável. Simples, funciona bem para este caso de uso (é mais "evitar duplicidade" do que lidar com disputa por um recurso limitado, como no caso de assentos de cinema).

**Opção B — Transação com isolamento explícito**
Usar transações com nível de isolamento `SERIALIZABLE` ou `SELECT ... FOR UPDATE` na linha da sessão, garantindo que verificações (ex: "sessão ainda aberta") e a escrita aconteçam de forma atômica.

**Opção C — Fila de processamento (para picos de carga)**
Em vez de escrever diretamente no banco a cada requisição, a API apenas valida e empilha a confirmação numa fila (Redis/Celery), e um worker processa as inserções de forma controlada. Reduz contenção direta no banco sob alta concorrência.

### 5.3 Como demonstrar isso na apresentação
1. Implementar primeiro **sem** proteção adequada e mostrar o problema (ex: script de teste de carga disparando 100 requisições simultâneas do mesmo aluno, mostrando registros duplicados ou erros)
2. Aplicar a correção (Opção A, B ou C)
3. Repetir o teste de carga e mostrar 0 duplicidades, com métricas de tempo de resposta antes/depois
4. Isso vira, literalmente, o gráfico de "otimização realizada" pedido no vídeo final

**Ferramenta sugerida para o teste de carga**: `locust` (Python, fácil de integrar ao ecossistema FastAPI) ou `k6`.

---

## 6. Processamento paralelo/assíncrono — onde aplicar

| Cenário | Abordagem técnica |
|---|---|
| Notificar N alunos quando a chamada abre | Celery task disparando `sendMulticast` do FCM em lote, ou dividindo em chunks processados por múltiplos workers |
| Gerar relatório de frequência de uma turma/período | `multiprocessing.Pool` ou Celery, dividindo por turma/aluno como unidade de trabalho paralela |
| Validar geolocalização de muitos alunos de uma vez (ex: reprocessar uma sessão) | Consulta em lote no PostGIS usando `ST_DWithin` com índice espacial, muito mais eficiente que calcular distância em Python linha a linha |
| Envio de e-mails periódicos (ex: relatório mensal para todos os professores) | Fila assíncrona (Celery) processando envios em paralelo, evitando travar o sistema principal |

---

## 7. Estrutura de pastas (backend)

A estrutura segue Clean Architecture organizada por módulos de domínio. Cada módulo é autocontido com suas quatro camadas (`domain/`, `application/`, `infra/`, `interface/`).

```
app/
├── main.py                        # ponto de entrada FastAPI, registra routers
│
├── shared/                        # conceitos compartilhados entre módulos
│   ├── value_objects/
│   │   ├── geo_point.py           # coordenada geográfica tipada
│   │   └── day_code.py            # value object do código do dia
│   └── enums/
│       ├── user_role.py           # admin, professor, aluno, coordenador
│       ├── session_status.py      # open, closed
│       └── notification_status.py # sent, failed
│
├── config/
│   ├── settings.py                # lê .env via pydantic-settings (único lugar)
│   ├── database.py                # engine e session factory async
│   └── redis.py                   # cliente Redis
│
├── infra/                         # infraestrutura transversal
│   ├── database/
│   │   ├── session.py             # AsyncSession factory, get_db dependency
│   │   └── base.py                # DeclarativeBase SQLAlchemy
│   ├── storage/
│   │   └── s3_client.py           # upload de fotos de evidência (S3/MinIO)
│   └── queue/
│       ├── celery_app.py          # instância Celery + configuração Redis broker
│       └── workers/
│           ├── notification_worker.py   # envia FCM em lote
│           └── report_worker.py         # gera relatórios de frequência
│
├── security/
│   ├── dependencies/
│   │   ├── current_user.py        # get_current_user() — Depends
│   │   └── require_role.py        # require_role("professor") — Depends
│   ├── jwt.py                     # criar e verificar tokens JWT
│   └── password.py                # hash e verificação de senha
│
└── modules/
    │
    ├── auth/
    │   ├── application/
    │   │   └── use_cases/
    │   │       └── login.py
    │   └── interface/
    │       ├── router.py
    │       └── schemas/
    │           └── login.py
    │
    ├── user/
    │   ├── domain/
    │   │   ├── entities/
    │   │   │   └── user.py
    │   │   └── repositories/
    │   │       └── user_repository.py     # Protocol / interface
    │   ├── application/
    │   │   └── use_cases/
    │   │       ├── create_user.py
    │   │       └── get_user.py
    │   ├── infra/
    │   │   ├── repositories/
    │   │   │   └── user_sqlalchemy_repository.py
    │   │   └── mappers/
    │   │       └── user_mapper.py
    │   └── interface/
    │       ├── router.py
    │       └── schemas/
    │           └── create_user.py
    │
    ├── class_/                        # módulo: turmas
    │   ├── domain/
    │   │   ├── entities/
    │   │   │   └── class_.py
    │   │   └── repositories/
    │   │       └── class_repository.py
    │   ├── application/
    │   │   └── use_cases/
    │   │       ├── create_class.py
    │   │       ├── enroll_student.py
    │   │       └── list_classes.py
    │   ├── infra/
    │   │   ├── repositories/
    │   │   │   └── class_sqlalchemy_repository.py
    │   │   └── mappers/
    │   │       └── class_mapper.py
    │   └── interface/
    │       ├── router.py
    │       └── schemas/
    │           └── create_class.py
    │
    ├── room/                          # módulo: salas com geolocalização
    │   ├── domain/
    │   │   ├── entities/
    │   │   │   └── room.py
    │   │   └── repositories/
    │   │       └── room_repository.py
    │   ├── application/
    │   │   └── use_cases/
    │   │       ├── create_room.py
    │   │       └── get_room.py
    │   ├── infra/
    │   │   ├── repositories/
    │   │   │   └── room_sqlalchemy_repository.py  # usa GeoAlchemy2
    │   │   └── mappers/
    │   │       └── room_mapper.py
    │   └── interface/
    │       ├── router.py
    │       └── schemas/
    │           └── create_room.py
    │
    ├── attendance/                    # módulo central: chamada
    │   ├── domain/
    │   │   ├── entities/
    │   │   │   ├── attendance_session.py
    │   │   │   └── attendance_record.py
    │   │   ├── repositories/
    │   │   │   ├── session_repository.py
    │   │   │   └── record_repository.py
    │   │   └── services/
    │   │       ├── geolocation_validator.py  # ST_DWithin puro no domínio (via port)
    │   │       ├── day_code_generator.py
    │   │       └── session_expiry_checker.py
    │   ├── application/
    │   │   └── use_cases/
    │   │       ├── open_session.py           # professor abre chamada
    │   │       ├── confirm_attendance.py     # aluno confirma presença
    │   │       └── close_session.py
    │   ├── infra/
    │   │   ├── repositories/
    │   │   │   ├── session_sqlalchemy_repository.py
    │   │   │   └── record_sqlalchemy_repository.py
    │   │   └── mappers/
    │   │       ├── session_mapper.py
    │   │       └── record_mapper.py
    │   └── interface/
    │       ├── router.py
    │       └── schemas/
    │           ├── open_session.py
    │           └── confirm_attendance.py
    │
    ├── notification/                  # módulo: notificações
    │   ├── domain/
    │   │   ├── entities/
    │   │   │   └── notification_log.py
    │   │   └── repositories/
    │   │       └── notification_repository.py
    │   ├── application/
    │   │   └── use_cases/
    │   │       └── notify_students.py        # dispara task Celery
    │   ├── infra/
    │   │   ├── repositories/
    │   │   │   └── notification_sqlalchemy_repository.py
    │   │   └── fcm_gateway.py                # integração Firebase Cloud Messaging
    │   └── interface/
    │       └── (sem router próprio — acionado internamente)
    │
    └── report/                        # módulo: relatórios de frequência
        ├── domain/
        │   └── services/
        │       └── frequency_calculator.py
        ├── application/
        │   └── use_cases/
        │       └── generate_report.py
        ├── infra/
        │   └── (queries de agregação via repositórios existentes)
        └── interface/
            ├── router.py
            └── schemas/
                └── report_response.py

alembic/
├── versions/
│   ├── 001_create_users.py
│   ├── 002_create_classes.py
│   ├── 003_create_rooms.py          # habilita PostGIS, cria índice GiST
│   ├── 004_create_attendance.py
│   └── 005_create_notifications.py
├── env.py
└── script.py.mako

tests/
├── unit/
│   ├── test_geolocation_validator.py  # valida lógica dentro/fora do raio
│   ├── test_day_code_generator.py
│   └── test_session_expiry.py
├── integration/
│   ├── test_confirm_attendance.py
│   └── test_open_session.py
└── e2e/
    └── test_concurrency.py            # 100 requisições simultâneas, 0 duplicatas

pyproject.toml
docker-compose.yml
.env.example
```

### Por que módulos por domínio em vez de pastas globais?

| Estrutura antiga (plana) | Estrutura nova (por módulo) |
|---|---|
| `models/` global com todos os modelos SQLAlchemy | Cada módulo tem seu `infra/repositories/` e `infra/mappers/` |
| `services/` global com toda regra de negócio | Cada módulo tem seu `domain/services/` e `application/use_cases/` |
| `api/routes/` global | Cada módulo tem seu `interface/router.py` |
| Acoplamento invisível entre módulos | Dependências explícitas via interfaces (`Protocol`) |

**Benefício direto para o TCC**: cada caso de uso (`confirm_attendance.py`, `open_session.py`) pode ser testado de forma completamente isolada, sem subir a API, banco ou Redis — basta mockar o repositório. Isso torna os testes de concorrência mais precisos e reproduzíveis.

---

## 8. Boas práticas de desenvolvimento para a equipe

### 8.1 Fluxo de trabalho em equipe (Git)
- Branch principal protegida (`main`), sem commit direto
- Uma branch por funcionalidade (`feature/attendance-confirmation`, `feature/geolocation-validation`)
- Pull Requests revisados por pelo menos um outro integrante antes do merge
- Commits pequenos e descritivos (evitar "ajustes" ou "fix" genéricos)

### 8.2 Ambiente de desenvolvimento
- Usar **Docker Compose** para subir localmente: API + PostgreSQL (ou usar direto o Neon em dev) + Redis, garantindo que todos os integrantes rodem o mesmo ambiente sem "na minha máquina funciona"
- Variáveis sensíveis (chaves do Firebase, connection string do banco) em `.env`, nunca commitadas — usar `.env.example` como referência

### 8.3 Testes mínimos recomendados
- Teste unitário da lógica de validação de geolocalização (distância dentro/fora do raio)
- Teste unitário da expiração do código do dia
- Teste de concorrência simulando múltiplas confirmações simultâneas (esse é o mais importante para o projeto — é a prova do componente de otimização)
- Teste de integração do fluxo completo: abrir sessão → confirmar presença → gerar relatório

### 8.4 Documentação técnica esperada
- README com instruções de execução (`docker-compose up`, variáveis de ambiente necessárias)
- Diagrama de arquitetura (like o da seção 1)
- Diagrama entidade-relacionamento do banco
- Documento explicando a estratégia de concorrência escolhida e os resultados do teste de carga (isso vira parte do TCC escrito e do vídeo)
- Documentação da API gerada automaticamente pelo FastAPI (`/docs`, Swagger/OpenAPI — já vem pronto, só precisa ser bem preenchida com descrições nos endpoints)

---

## 9. Ordem sugerida de implementação (alinhada às Sprints da disciplina)

1. **Setup inicial**: repositório, Docker Compose, FastAPI básico, conexão com Neon/PostGIS
2. **Autenticação e perfis de usuário** (JWT, roles)
3. **CRUD de turmas, salas e vínculo aluno-turma**
4. **Abertura de sessão de chamada + geração de código do dia**
5. **Endpoint de confirmação de presença SEM proteção de concorrência** (versão inicial, para depois comparar)
6. **Validação de geolocalização com PostGIS**
7. **Teste de carga demonstrando o problema de concorrência**
8. **Implementação da correção de concorrência (Opção A, B ou C)**
9. **Novo teste de carga comprovando a correção — documentar métricas**
10. **Notificações push (FCM) via fila assíncrona**
11. **Relatórios de frequência (processamento em lote)**
12. **Envio de e-mails periódicos**
13. **Painel web do professor + app mobile do aluno (podem ser desenvolvidos em paralelo com o backend, consumindo endpoints mockados no início)**
14. **Testes finais, documentação e preparação dos vídeos**

---

## 10. Riscos técnicos e como mitigar

| Risco | Mitigação |
|---|---|
| Equipe sem experiência prévia em Celery/Redis | Começar com `BackgroundTasks` do FastAPI; migrar só se sobrar tempo |
| GPS impreciso em ambientes fechados (salas de aula) | Definir raio de tolerância generoso (ex: 50-100m) e permitir configuração por sala |
| Falta de conta Apple Developer para testar push no iOS | Focar demonstração em Android; mencionar limitação no vídeo, se necessário |
| PostGIS não habilitado corretamente no Neon | Testar `CREATE EXTENSION postgis;` logo no Sprint 1, não deixar para depois |
| Teste de concorrência mal executado (não reflete cenário real) | Simular volume realista de alunos por turma (ex: 40-60), não um número artificialmente pequeno |
