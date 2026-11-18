# Locus

Sistema de chamada acadêmica com validação por geolocalização. O professor abre a chamada no painel, o aluno confirma no celular com o código do dia e a localização, e o Locus registra a presença, a auditoria e a frequência da turma.

O produto se chama **Locus**. Ele está dividido em três repositórios:

| Repositório | O que é | Endereço |
|---|---|---|
| `classroom-api` | API, banco, regras de negócio e tarefas em segundo plano | https://github.com/rodrigoacm10/classroom-api |
| `classroom-web` | Painel do professor e da administração | https://github.com/rodrigoacm10/classroom-web |
| `classroom-mobile` | Aplicativo do aluno | https://github.com/rodrigoacm10/classroom-mobile |

## O problema

A chamada em papel gasta tempo de aula e não impede que um colega responda por outro. Numa chamada digital simples, dezenas de alunos confirmam ao mesmo tempo, e o sistema não pode gravar a mesma presença duas vezes nem perder um registro. No fim do período, calcular a frequência da turma inteira vira uma conta grande.

## Como funciona

1. A instituição cadastra salas com um ponto no mapa e um raio. As turmas ficam ligadas a uma sala e a um professor.
2. O professor, ou um administrador, abre a chamada. O sistema gera um código de seis caracteres e uma janela de tempo. Os alunos matriculados que registraram o aplicativo recebem um aviso no celular.
3. O aluno informa o código. O aplicativo envia a localização. A API aceita a confirmação quando a chamada está aberta, o código confere, a matrícula está ativa e aquele aluno ainda não confirmou.
4. Localização ruim ou aparelho suspeito não bloqueiam o aluno. O registro entra como irregular e o professor valida ou rejeita depois.
5. Presença rejeitada conta como falta. O relatório de frequência mostra a taxa, quem está abaixo de 75% e a distância média das confirmações até a sala.

Há quatro papéis. O administrador gere a instituição, os membros e os convites. O coordenador consulta. O professor conduz as próprias turmas e as chamadas. O aluno confirma a presença e acompanha o próprio histórico. Uma mesma pessoa pode participar de mais de uma instituição e trocar de contexto depois do login.

## O que cada parte faz

**API.** Autenticação com token, recuperação de senha por código, instituições, salas, turmas, matrículas, chamadas, convites, membros, relatório de frequência e registro do token de notificação. A confirmação duplicada é barrada por uma restrição única no banco. O aviso de chamada, o fechamento das chamadas vencidas e a limpeza de fotos pendentes rodam em segundo plano.

**Painel web.** Login, escolha da instituição, dashboard, salas no mapa, turmas, abertura e acompanhamento da chamada, auditoria da presença, alunos, membros, convites, relatório com exportação e configurações da instituição. Professor e aluno que abrem uma rota restrita, como Convites, veem acesso negado.

**Aplicativo.** Login, escolha da instituição, aviso de chamada, confirmação com código, GPS e foto opcional, histórico e perfil. O aviso de chamada está disponível no Android. O iOS fica de fora desta versão porque exige conta paga de desenvolvedor Apple.

A distância entre o aluno e a sala é calculada com Haversine. O PostGIS entra no índice espacial da sala, para a consulta geográfica não varrer a tabela inteira.

## Processamento do relatório

O relatório de frequência é o componente de processamento do projeto. Para cada aluno, o cálculo da distância é independente dos outros. Os dados sobem para a memória, o cálculo roda em paralelo e o resultado é agregado.

Há três estratégias, escolhidas pela variável `REPORT_STRATEGY` na subida do processo: sequencial, pool de processos e pool de threads com NumPy. O padrão é o pool de processos. A resposta do relatório informa a estratégia usada, a quantidade de workers e a duração. CUDA e OpenCL não são usados: o ambiente de publicação não oferece GPU, e a carga é de muitos cálculos pequenos, bem atendida por CPU.

## Tecnologias

| Parte | Tecnologias |
|---|---|
| API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 com PostGIS, Redis, Celery |
| Serviços | Firebase Cloud Messaging, Cloudflare R2 para as fotos, Resend para e-mail |
| Painel | Next.js 16, React 19, TypeScript, Tailwind CSS 4, Leaflet |
| Aplicativo | Expo, React Native, TypeScript, expo-router |

## Equipe

- Carlos Alberto Ramalho Bezerra Neto, Product Owner e Scrum Master
- Rodrigo Andrade Cavalcante Muniz, API, banco de dados e regras de negócio
- Eliel Lucas Trajano Neto, aplicativo, painel e documentação

## Como rodar

Suba nesta ordem: banco e Redis, API, worker, painel e aplicativo. Os três repositórios ficam em pastas irmãs.

Requisitos: Docker e Docker Compose, Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 20 ou superior e npm. O aviso de chamada no celular pede um aparelho Android ou um build de desenvolvimento. O Expo Go não entrega o token nativo do Firebase.

### 1. API (`classroom-api`)

```bash
git clone https://github.com/rodrigoacm10/classroom-api.git
cd classroom-api
uv sync
cp .env.example .env
docker compose up -d
uv run alembic upgrade head
```

O Compose sobe PostgreSQL com PostGIS na porta 5432 e Redis na porta 6379. O `.env.example` já aponta para esse banco local. Troque `JWT_SECRET`. E-mail, Firebase e Cloudflare R2 só são necessários para convite, aviso de chamada e foto. Sem essas chaves, login, turmas e chamada no painel seguem funcionando.

Dados de demonstração, se quiser o painel preenchido:

```bash
uv run python scripts/seed_dashboard_data.py
```

API e worker, em terminais separados:

```bash
uv run uvicorn src.main:app --reload
uv run celery -A src.infra.tasks.celery_app worker -B -l info
```

A API fica em http://localhost:8000. A documentação interativa fica em http://localhost:8000/docs.

O worker com `-B` também liga o agendador: fecha chamadas vencidas e limpa fotos de evidência que ficaram pendentes. Sem esse processo, o aviso não sai e a chamada não fecha sozinha.

Testes e benchmark do relatório:

```bash
uv run pytest
uv run python scripts/benchmark_report.py --students 5000 --sessions 40 --intensity 40
```

Os testes de ponta a ponta esperam um PostgreSQL de teste em `localhost:5432`, no banco `classroom_test`, com o mesmo usuário do Compose (`classroom` / `classroom`).

### 2. Painel web (`classroom-web`)

Com a API já no ar:

```bash
git clone https://github.com/rodrigoacm10/classroom-web.git
cd classroom-web
cp .env.example .env.local
npm install
npm run dev
```

Abra http://localhost:3000. `NEXT_PUBLIC_API_URL` aponta para http://localhost:8000. O painel não tem banco próprio.

```bash
npm run lint
npx tsc --noEmit
```

### 3. Aplicativo (`classroom-mobile`)

Com a API já no ar:

```bash
git clone https://github.com/rodrigoacm10/classroom-mobile.git
cd classroom-mobile
cp .env.example .env
npm install
npx expo start
```

`EXPO_PUBLIC_API_URL` é o endereço da API, sem barra no final.

| Onde o app roda | Valor de `EXPO_PUBLIC_API_URL` |
|---|---|
| Emulador Android | `http://10.0.2.2:8000` |
| Simulador iOS ou navegador | `http://localhost:8000` |
| Celular na mesma rede Wi-Fi | `http://IP-DA-MAQUINA:8000` |

O aplicativo não tem banco próprio. Para o aviso de chamada, use um build de desenvolvimento no Android, com o arquivo de credenciais do Firebase configurado na API (`FIREBASE_CREDENTIALS_PATH` ou `FIREBASE_CREDENTIALS_JSON`).

## Estrutura

```text
classroom-api/
  src/modules/    autenticação, chamada, matrícula, relatório, convite, notificação
  src/infra/      banco, Celery e integrações
  src/security/   token e permissões
  alembic/        migrações
  tests/          testes unitários, de integração e de ponta a ponta

classroom-web/
  src/app/        rotas do login e do painel
  src/modules/    telas de cada funcionalidade
  src/services/   chamadas à API

classroom-mobile/
  src/app/        login, instituição, início, chamada, histórico e perfil
  src/lib/        cliente da API, notificação e foto
  src/services/   chamadas à API
```
