# Task 11 — Módulo de Relatórios de Frequência com Paralelismo Real (CPU)

> **Objetivo**: Implementar o módulo `report`, responsável por gerar relatórios de frequência por
> aluno e por turma, combinando duas coisas: (1) agregação de presença/falta a partir dos
> `AttendanceRecord` e `Enrollment` já existentes, e (2) métricas geoespaciais recalculadas
> (distância Haversine) que exigem processamento matemático repetitivo por confirmação.
> A geração do relatório usa **paralelismo real de CPU** — múltiplos processos e, opcionalmente,
> múltiplas threads sobre código vetorizado — como motor de cálculo, com estratégia trocável para
> permitir benchmark comparativo (sequencial vs. paralelo).
>
> **Entrega esperada desta etapa**:
>
> - `POST /tenants/{tenant_id}/subject-classes/{subject_class_id}/reports/frequency` — gera o
>   relatório de frequência da turma (todos os alunos matriculados).
> - `GET /tenants/{tenant_id}/subject-classes/{subject_class_id}/reports/frequency/{tenant_member_id}`
>   — detalhe do relatório de um aluno específico.
> - Motor de cálculo com 3 estratégias trocáveis: `SequentialStrategy` (baseline),
>   `ProcessPoolStrategy` (paralelismo real via múltiplos núcleos) e `ThreadPoolNumpyStrategy`
>   (paralelismo real via threads, válido porque o cálculo vetorizado libera o GIL).
> - Persistência do histórico de execuções (`report_generation_logs`) com estratégia usada,
>   número de workers, quantidade de itens processados e duração — para gerar prova numérica
>   automática sem depender de script manual no dia da gravação do vídeo.
> - Script de benchmark dedicado (`scripts/benchmark_report.py`) com dataset sintético, para gerar
>   o gráfico de "otimizações realizadas" do vídeo do TCC.

> [!WARNING]
> **Pré-requisito**: Esta etapa depende dos módulos [`attendance`](./6-attendance.md) e
> [`enrollment`](./5-subject-class-enrollment.md), que já existem e **não são alterados**. O
> módulo `report` apenas **lê** dados de `AttendanceRecord`, `AttendanceSession`, `Enrollment` e
> `Room` — nenhuma tabela existente é modificada.

> [!NOTE]
> **Fora do escopo desta etapa:**
>
> - 📄 **Exportação em PDF/CSV** — o endpoint retorna JSON; exportação fica para etapa futura.
> - 📧 **Envio periódico do relatório por e-mail** — mencionado no contexto do TCC, mas não faz
>   parte desta entrega; pode reaproveitar o `infra/email/resend_client.py` já existente depois.
> - 🖥️ **CUDA / GPU** — o Railway (ambiente de deploy do projeto) não oferece GPU nos planos
>   padrão. Paralelismo em GPU não é usado em produção nesta etapa. Se a equipe quiser demonstrar
>   CUDA/OpenCL adicionalmente, isso deve ser um script **local**, isolado, e apresentado como tal
>   — nunca como parte do fluxo deployado.
> - 🏢 **Relatório institucional (todas as turmas do tenant de uma vez)** — desenhado como extensão
>   opcional na Parte 9, não é obrigatório para esta entrega.
> - 🗺️ **Simulação de raio de tolerância retroativo** (mudar `tolerance_radius_meters` e reclassificar
>   histórico) — é uma feature de domínio do módulo `attendance`, não deste módulo. Ver nota na
>   Parte 2 sobre dívida técnica.

---

## Por que este módulo exige paralelismo REAL (não Celery, não `asyncio`)

O projeto já usa dois tipos de "processamento em background" que **não contam** como o paralelismo
exigido pela disciplina de Tópicos Avançados:

| Mecanismo já usado no projeto | Onde | Por que NÃO é o paralelismo pedido |
|---|---|---|
| `Celery` + `Redis` | Notificações FCM (`infra/tasks/`) | É fila distribuída — resolve "não bloquear o HTTP", não usa múltiplos núcleos para acelerar uma conta |
| `async`/`await` do FastAPI | Toda a API | É concorrência de I/O em **uma única thread** — enquanto espera o banco responder, atende outra requisição. CPU fica ociosa, não paralela |
| `asyncio.gather` | (não usado ainda, mas seria a tentação natural aqui) | Mesmo problema do item acima — múltiplas espera de I/O simultâneas, não múltiplos núcleos calculando |

O professor de Tópicos Avançados pediu explicitamente **núcleos e threads** (`multiprocessing`,
`concurrent.futures`, ou CUDA/OpenCL) — ou seja, processamento onde o sistema operacional
efetivamente agenda trabalho em mais de um núcleo físico da CPU **ao mesmo tempo**.

```text
Concorrência (asyncio/Celery)              Paralelismo real (o que este módulo implementa)
────────────────────────────               ────────────────────────────────────────────────
1 núcleo                                    Núcleo 1   Núcleo 2   Núcleo 3   Núcleo 4
  │                                            │          │          │          │
  ├─ espera banco (sessão 1) ┐                 ▼          ▼          ▼          ▼
  ├─ espera banco (sessão 2) │ intercalado   calcula    calcula    calcula    calcula
  └─ espera banco (sessão 3) ┘               aluno 1-10 aluno 11-20 aluno 21-30 aluno 31-40
                                                  │          │          │          │
     (CPU ociosa na maior parte do tempo)         └──────────┴────┬─────┴──────────┘
                                                              junta os resultados
```

### Por que Python precisa de **processos**, não apenas threads, para código puro

O interpretador CPython tem o **GIL** (*Global Interpreter Lock*): apenas uma thread executa
bytecode Python por vez, mesmo em máquinas com 8 ou 16 núcleos. Isso significa que
`threading.Thread` **não acelera** um cálculo escrito em Python puro (loops com `math.sin`,
`math.cos`, etc.) — as threads competem pelo mesmo núcleo.

Existem duas formas legítimas de obter paralelismo real em Python, e este módulo implementa **as
duas**, para cobrir explicitamente "núcleos e threads" como o professor pediu:

| Abordagem | Como contorna o GIL | Usada neste módulo como |
|---|---|---|
| `multiprocessing` / `ProcessPoolExecutor` | Cada processo tem seu **próprio interpretador e seu próprio GIL** — são processos de SO reais, escalonados em núcleos diferentes | `ProcessPoolStrategy` |
| Threads sobre código vetorizado (NumPy) | Funções do NumPy são implementadas em C e **liberam o GIL** durante o cálculo pesado — múltiplas threads Python podem então rodar em paralelo dentro dessas chamadas | `ThreadPoolNumpyStrategy` |

> **Threads em Python puro (sem NumPy) não são implementadas neste módulo** porque seriam uma
> demonstração falsa de paralelismo — o código rodaria concorrente, não paralelo, e um professor
> de Tópicos Avançados que entenda de GIL identificaria isso imediatamente. Preferimos não incluir
> essa variante a incluir uma variante que não faz o que diz fazer.

---

## Conceito central — qual é a unidade de trabalho paralelizável

O cálculo do relatório de um aluno (frequência, faltas, métricas geoespaciais) **não depende** do
cálculo de nenhum outro aluno. Isso é o que se chama de problema **embaraçosamente paralelo**
(*embarrassingly parallel*): dividir o trabalho em N pedaços independentes e processá-los em
paralelo sem nenhuma coordenação entre os pedaços.

```text
Turma "POO" — 40 alunos matriculados, 20 sessões de chamada no semestre
        │
        ▼
FASE 1 — I/O (sequencial, uma única query — NUNCA paralelizada)
  Busca TODOS os AttendanceRecord + Enrollment + Room da turma de uma vez
        │
        ▼
FASE 2 — CPU (paralela — o foco desta task)
  Para CADA aluno, de forma independente:
    - localizar suas confirmações dentre os registros já carregados em memória
    - contar presença / falta / irregularidades
    - recalcular a distância Haversine de cada confirmação até a sala
    - calcular distância média, nº de confirmações no limite do raio
        │
        ▼
FASE 3 — Agregação final (sequencial, rápida — depende de todos os resultados da Fase 2)
  Ordenar por risco, calcular média da turma, montar resposta
```

> **Por que a Fase 2 inclui recálculo de distância, se ela já está salva no banco?**
> O relatório poderia apenas ler `distance_meters` já persistido em `AttendanceRecord` — isso seria
> suficiente para o produto, mas seria uma conta leve demais (poucas somas) para justificar
> paralelismo de forma convincente. Recalcular a distância via Haversine para cada confirmação do
> semestre transforma a Fase 2 em um trabalho matemático real (múltiplos `sin`/`cos`/`arcsin` por
> item), e ainda produz uma métrica de auditoria legítima: **distância média das confirmações** e
> **quantas ficaram no limite do raio de tolerância** — útil para o professor identificar alunos que
> sistematicamente confirmam próximo do limite (indício de fraude sutil).
>
> [!NOTE]
> **Nota de dívida técnica assumida deliberadamente**: a regra de cálculo geoespacial
> (`haversine_distance`, classificação dentro/fora do raio) já existe e pertence, por domínio, ao
> módulo `attendance` (ver `record_sqlalchemy_repository.py`). Para esta entrega do TCC, a função
> pura de cálculo é **duplicada/isolada** dentro de `modules/report/domain/services/geo_metrics.py`
> em vez de importada de `attendance`, para manter os dois módulos desacoplados dentro do prazo.
> Em uma refatoração futura (pós-TCC), essa função deve ser movida para `shared/` e importada por
> ambos os módulos, eliminando a duplicação. Isso é assumido conscientemente — não é um erro
> descoberto depois.

---

## Modelagem de Dados

### Nenhuma tabela existente é alterada

O módulo é **somente leitura** sobre `attendance_sessions`, `attendance_records`,
`subject_class_enrollments`, `rooms` e `tenant_members`. Nenhuma migration é necessária nessas
tabelas.

### Nova tabela — `report_generation_logs` (evidência de benchmark automática)

```
report_generation_logs
  ├── id                  UUID (PK)
  ├── tenant_id           FK → tenants.id             ON DELETE CASCADE
  ├── subject_class_id    FK → subject_classes.id     ON DELETE CASCADE
  ├── strategy            VARCHAR(30)     -- "sequential" | "process_pool" | "thread_pool_numpy"
  ├── workers_used         INTEGER         -- nº de processos/threads (1 se sequencial)
  ├── items_processed      INTEGER         -- nº de alunos processados nesta execução
  ├── duration_ms           FLOAT           -- tempo total da Fase 2 (cálculo), em milissegundos
  ├── created_at            TIMESTAMPTZ DEFAULT now()
```

> **Por que persistir isso em vez de só medir num script?**
> Toda vez que o endpoint de relatório é chamado (em qualquer ambiente — dev, Railway, durante os
> testes manuais da equipe), a duração e a estratégia usada ficam registradas. Isso significa que,
> ao trocar a variável de ambiente `REPORT_STRATEGY` entre `sequential` e `process_pool` durante os
> testes normais de desenvolvimento, a equipe **já está gerando a evidência do benchmark** sem
> precisar lembrar de rodar nada especial no dia da gravação — só consultar
> `SELECT strategy, workers_used, items_processed, duration_ms FROM report_generation_logs ORDER BY created_at`.

---

## Arquitetura do Módulo

```
src/
├── shared/
│   └── parallel/                                       ← [NEW] Motor de paralelismo reutilizável
│       ├── __init__.py
│       ├── compute_strategy.py                         ← Protocol ComputeStrategy[T, R]
│       ├── sequential_strategy.py                      ← Baseline (benchmark)
│       ├── process_pool_strategy.py                    ← multiprocessing real (núcleos)
│       ├── thread_pool_numpy_strategy.py               ← threads reais sobre NumPy (libera o GIL)
│       └── cpu_budget.py                                ← nº seguro de workers em container (cgroups)
│
├── infra/
│   └── database/
│       └── models/
│           └── report_generation_log.py                ← [NEW] Model SQLAlchemy
│
└── modules/
    └── report/
        ├── domain/
        │   ├── entities/
        │   │   ├── student_attendance_data.py          ← [NEW] Dados brutos de 1 aluno (picklable)
        │   │   ├── student_report.py                    ← [NEW] Resultado calculado de 1 aluno
        │   │   └── class_report.py                      ← [NEW] Agregado da turma
        │   └── services/
        │       └── geo_metrics.py                       ← [NEW] Haversine + cálculo puro (função picklable)
        │
        ├── application/
        │   └── use_cases/
        │       ├── generate_class_report.py             ← [NEW] Orquestra Fases 1/2/3
        │       └── get_student_report.py                ← [NEW] Relatório de 1 aluno específico
        │
        ├── infra/
        │   └── repositories/
        │       └── report_data_repository.py            ← [NEW] Query única, carrega tudo em memória
        │
        └── interface/
            ├── router.py                                ← [NEW] 2 endpoints
            └── schemas/
                └── report_schemas.py                     ← [NEW] Schemas Pydantic de resposta

alembic/versions/
  └── XXX_create_report_generation_logs.py               ← [NEW] Migration

scripts/
  └── benchmark_report.py                                 ← [NEW] Dataset sintético + medição p/ vídeo

tests/
├── unit/
│   ├── shared/parallel/
│   │   ├── test_sequential_strategy.py
│   │   ├── test_process_pool_strategy.py
│   │   └── test_thread_pool_numpy_strategy.py
│   └── modules/report/
│       ├── test_geo_metrics.py
│       └── test_generate_class_report_use_case.py
├── integration/modules/report/
│   └── test_report_data_repository.py
└── e2e/modules/report/
    └── test_report_router.py
```

---

## Parte 1 — Motor de Paralelismo Reutilizável (`shared/parallel/`)

Construído uma única vez e reaproveitado por qualquer módulo futuro que precise da mesma técnica
(o precedente no projeto é `shared/events/`, usado pelo event bus da Task 9).

### 1.1 `compute_strategy.py` — a abstração

```python
# src/shared/parallel/compute_strategy.py
from typing import Protocol, TypeVar

T = TypeVar("T")   # tipo do item de entrada (ex: StudentAttendanceData)
R = TypeVar("R")   # tipo do resultado (ex: StudentReport)


class ComputeStrategy(Protocol[T, R]):
    """
    Executa uma função pura sobre uma lista de itens independentes entre si,
    devolvendo a lista de resultados na mesma ordem. A implementação decide
    COMO distribuir o trabalho (sequencial, múltiplos processos, múltiplas threads).
    """

    def compute(self, items: list[T], fn) -> list[R]:
        ...

    @property
    def name(self) -> str:
        """Identificador usado no report_generation_logs (ex: 'process_pool')."""
        ...

    @property
    def workers_used(self) -> int:
        """Nº de processos/threads efetivamente usados nesta execução."""
        ...
```

### 1.2 `cpu_budget.py` — nº seguro de workers em container

```python
# src/shared/parallel/cpu_budget.py
import os


def cpu_budget() -> int:
    """
    Retorna o nº de núcleos realmente disponíveis para este processo.

    IMPORTANTE: `os.cpu_count()` retorna o total de núcleos da MÁQUINA HOST,
    não a fração de CPU alocada ao container pelo provedor de deploy (Railway,
    Docker, etc.). Se o plano do Railway aloca, por exemplo, 1 vCPU e o código
    usa os.cpu_count() (que pode reportar 8, o total do host físico), o
    ProcessPoolExecutor criaria 8 processos disputando 1 núcleo real — o
    resultado seria PIOR que a versão sequencial, não melhor.

    `os.sched_getaffinity(0)` respeita a máscara de CPU/cgroup atribuída ao
    processo atual (disponível em Linux — o SO de todo container Docker),
    sendo a fonte mais confiável em ambiente de produção.
    """
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except AttributeError:
        # macOS/Windows não implementam sched_getaffinity
        return max(1, os.cpu_count() or 1)
```

### 1.3 `sequential_strategy.py` — baseline

```python
# src/shared/parallel/sequential_strategy.py
from shared.parallel.compute_strategy import ComputeStrategy


class SequentialStrategy(ComputeStrategy):
    """Baseline sem paralelismo — usada para medir o ganho das outras estratégias."""

    def compute(self, items: list, fn) -> list:
        return [fn(item) for item in items]

    @property
    def name(self) -> str:
        return "sequential"

    @property
    def workers_used(self) -> int:
        return 1
```

### 1.4 `process_pool_strategy.py` — paralelismo real via núcleos

```python
# src/shared/parallel/process_pool_strategy.py
from concurrent.futures import ProcessPoolExecutor

from shared.parallel.compute_strategy import ComputeStrategy
from shared.parallel.cpu_budget import cpu_budget


class ProcessPoolStrategy(ComputeStrategy):
    """
    Divide o trabalho entre múltiplos processos do sistema operacional.
    Cada processo tem seu próprio interpretador Python e seu próprio GIL,
    portanto o SO efetivamente escalona os processos em núcleos distintos.

    Requisitos para `fn` e para cada item de `items`:
      - `fn` deve ser uma função de módulo (não lambda, não método de instância)
        para ser "picklable" — o multiprocessing serializa a função e os dados
        para enviar a cada processo filho.
      - Cada item deve conter apenas dados simples (dataclass com tipos
        primitivos), nunca uma conexão de banco ou sessão SQLAlchemy.
    """

    def __init__(self, max_workers: int | None = None) -> None:
        self._max_workers = max_workers or cpu_budget()

    def compute(self, items: list, fn) -> list:
        if not items:
            return []
        with ProcessPoolExecutor(max_workers=self._max_workers) as pool:
            return list(pool.map(fn, items))

    @property
    def name(self) -> str:
        return "process_pool"

    @property
    def workers_used(self) -> int:
        return self._max_workers
```

### 1.5 `thread_pool_numpy_strategy.py` — paralelismo real via threads

Esta estratégia só é válida porque o cálculo pesado (Haversine) é reescrito de forma **vetorizada**
com NumPy. As operações de array do NumPy são implementadas em C e liberam o GIL durante a
execução, permitindo que múltiplas threads Python rodem de fato em paralelo dentro dessas chamadas.

```python
# src/shared/parallel/thread_pool_numpy_strategy.py
from concurrent.futures import ThreadPoolExecutor

from shared.parallel.compute_strategy import ComputeStrategy
from shared.parallel.cpu_budget import cpu_budget


class ThreadPoolNumpyStrategy(ComputeStrategy):
    """
    Divide o trabalho entre múltiplas threads do sistema operacional.

    Só produz paralelismo real se `fn` invocar operações NumPy vetorizadas
    (que liberam o GIL). Não deve ser usada com funções em Python puro —
    nesse caso threads apenas alternam contexto, sem ganho de velocidade.

    Vantagem sobre ProcessPoolStrategy: sem custo de serialização/IPC entre
    processos (threads compartilham memória), então tem menos overhead para
    volumes menores de trabalho.
    """

    def __init__(self, max_workers: int | None = None) -> None:
        self._max_workers = max_workers or cpu_budget()

    def compute(self, items: list, fn) -> list:
        if not items:
            return []
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            return list(pool.map(fn, items))

    @property
    def name(self) -> str:
        return "thread_pool_numpy"

    @property
    def workers_used(self) -> int:
        return self._max_workers
```

---

## Parte 2 — Cálculo Geoespacial Puro (`modules/report/domain/services/geo_metrics.py`)

Duas implementações da mesma matemática: uma em Python puro (usada por `ProcessPoolStrategy`) e
uma vetorizada em NumPy (usada por `ThreadPoolNumpyStrategy`). Ambas devem produzir o mesmo
resultado numérico — isso é validado em teste (ver Parte 9).

```python
# src/modules/report/domain/services/geo_metrics.py
"""
Funções puras de cálculo geoespacial. NÃO importam FastAPI, SQLAlchemy, nem
nenhuma infraestrutura — podem rodar isoladas em qualquer processo/thread.

NOTA DE DÍVIDA TÉCNICA: esta lógica é conceitualmente do domínio `attendance`
(mesma fórmula usada em record_sqlalchemy_repository.py). Duplicada aqui
deliberadamente para manter os módulos desacoplados dentro do prazo do TCC.
Mover para shared/ em uma refatoração futura.
"""
import math

import numpy as np

EARTH_RADIUS_METERS = 6_371_000.0


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Versão em Python puro — usada dentro de processos (ProcessPoolStrategy)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_METERS * c


def haversine_distance_vectorized(
    lats: np.ndarray, lons: np.ndarray, room_lat: float, room_lon: float
) -> np.ndarray:
    """
    Versão vetorizada com NumPy — usada dentro de threads (ThreadPoolNumpyStrategy).
    Calcula a distância de N pontos para a mesma sala em uma única chamada,
    sem loop Python explícito. As operações trigonométricas do NumPy
    (np.sin, np.cos, np.arcsin) são executadas em C e liberam o GIL.
    """
    phi1 = np.radians(lats)
    phi2 = np.radians(room_lat)
    dphi = np.radians(room_lat - lats)
    dlambda = np.radians(room_lon - lons)

    a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(a))
    return EARTH_RADIUS_METERS * c


def compute_student_geo_metrics(
    distances: list[float], tolerance_radius_meters: float
) -> dict:
    """Agrega as distâncias recalculadas de um aluno em métricas de auditoria."""
    if not distances:
        return {"avg_distance_meters": 0.0, "confirmations_near_limit": 0}

    avg_distance = sum(distances) / len(distances)
    near_limit_threshold = tolerance_radius_meters * 0.9  # dentro de 90% do limite
    near_limit_count = sum(1 for d in distances if d >= near_limit_threshold)

    return {
        "avg_distance_meters": round(avg_distance, 2),
        "confirmations_near_limit": near_limit_count,
    }
```

---

## Parte 3 — Entidades de Domínio (`modules/report/domain/entities/`)

### 3.1 `student_attendance_data.py` — dado bruto, picklable

```python
# src/modules/report/domain/entities/student_attendance_data.py
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class RawConfirmation:
    """Dado mínimo de uma confirmação — só o necessário para o cálculo."""
    latitude: float
    longitude: float
    record_status: str  # "regular" | "irregular" | "approved" | "rejected"


@dataclass
class StudentAttendanceData:
    """
    Entrada para a Fase 2 (cálculo). Contém apenas tipos primitivos/dataclasses
    simples — obrigatório para ser serializável entre processos (pickle).
    NUNCA deve conter uma sessão SQLAlchemy ou qualquer objeto de infraestrutura.
    """
    tenant_member_id: UUID
    student_name: str
    total_sessions: int
    confirmations: list[RawConfirmation] = field(default_factory=list)
    room_lat: float = 0.0
    room_lon: float = 0.0
    tolerance_radius_meters: float = 50.0
```

### 3.2 `student_report.py` — resultado calculado

```python
# src/modules/report/domain/entities/student_report.py
from dataclasses import dataclass
from uuid import UUID


@dataclass
class StudentReport:
    tenant_member_id: UUID
    student_name: str
    total_present: int
    total_absent: int
    total_irregular: int
    frequency_rate: float          # 0.0 a 1.0
    at_risk: bool                  # frequency_rate < limite institucional (padrão 0.75)
    avg_distance_meters: float     # métrica geoespacial recalculada
    confirmations_near_limit: int  # nº de confirmações a ≥90% do raio de tolerância
```

### 3.3 `class_report.py` — agregado da turma

```python
# src/modules/report/domain/entities/class_report.py
from dataclasses import dataclass
from uuid import UUID

from modules.report.domain.entities.student_report import StudentReport


@dataclass
class ClassReport:
    subject_class_id: UUID
    total_students: int
    class_average_frequency: float
    students_at_risk: int
    students: list[StudentReport]

    # Metadados de execução — usados para popular report_generation_logs
    strategy_used: str
    workers_used: int
    duration_ms: float
```

As funções puras de cálculo (Fase 2) recebem `StudentAttendanceData` e devolvem `StudentReport` —
isso é o que é passado para `ComputeStrategy.compute(items, fn)`:

```python
# src/modules/report/domain/services/student_calculator.py  (função-alvo do paralelismo)
from modules.report.domain.entities.student_attendance_data import StudentAttendanceData
from modules.report.domain.entities.student_report import StudentReport
from modules.report.domain.services.geo_metrics import (
    compute_student_geo_metrics,
    haversine_distance,
)

RISK_THRESHOLD = 0.75  # 75% de frequência mínima — configurável por tenant em etapa futura


def calculate_student_report(data: StudentAttendanceData) -> StudentReport:
    """
    Função pura — roda IDENTICAMENTE em processo separado, thread separada
    ou chamada direta (sequencial). Não faz I/O de nenhuma espécie.
    """
    valid = [c for c in data.confirmations if c.record_status in ("regular", "approved")]
    irregular = [c for c in data.confirmations if c.record_status == "irregular"]

    present = len(valid)
    absent = data.total_sessions - len(data.confirmations)
    rate = present / data.total_sessions if data.total_sessions > 0 else 0.0

    distances = [
        haversine_distance(c.latitude, c.longitude, data.room_lat, data.room_lon)
        for c in data.confirmations
    ]
    geo = compute_student_geo_metrics(distances, data.tolerance_radius_meters)

    return StudentReport(
        tenant_member_id=data.tenant_member_id,
        student_name=data.student_name,
        total_present=present,
        total_absent=absent,
        total_irregular=len(irregular),
        frequency_rate=round(rate, 4),
        at_risk=rate < RISK_THRESHOLD,
        avg_distance_meters=geo["avg_distance_meters"],
        confirmations_near_limit=geo["confirmations_near_limit"],
    )
```

---

## Parte 4 — Repositório de Dados (`infra/repositories/report_data_repository.py`)

Responsável **exclusivamente** pela Fase 1 (I/O). Executa uma única query eficiente que já traz
tudo agrupado por aluno — nunca é paralelizado, e nunca abre conexão dentro dos processos/threads
de cálculo.

```python
# src/modules/report/infra/repositories/report_data_repository.py
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.attendance_record import AttendanceRecordModel
from infra.database.models.attendance_session import AttendanceSessionModel
from infra.database.models.enrollment import EnrollmentModel
from infra.database.models.room import RoomModel
from infra.database.models.tenant_member import TenantMemberModel
from infra.database.models.user import UserModel
from modules.report.domain.entities.student_attendance_data import (
    RawConfirmation,
    StudentAttendanceData,
)


class ReportDataRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load_class_data(
        self, tenant_id: UUID, subject_class_id: UUID
    ) -> list[StudentAttendanceData]:
        """
        Uma única ida ao banco. Monta a estrutura completa em memória.
        A partir daqui, NENHUMA outra query é feita — o cálculo (Fase 2) opera
        inteiramente sobre os dados já carregados.
        """
        total_sessions_stmt = (
            select(AttendanceSessionModel.id)
            .where(AttendanceSessionModel.subject_class_id == subject_class_id)
        )
        session_ids = (await self.session.execute(total_sessions_stmt)).scalars().all()
        total_sessions = len(session_ids)

        enrollments_stmt = (
            select(EnrollmentModel, TenantMemberModel, UserModel)
            .join(TenantMemberModel, TenantMemberModel.id == EnrollmentModel.tenant_member_id)
            .join(UserModel, UserModel.id == TenantMemberModel.user_id)
            .where(
                EnrollmentModel.subject_class_id == subject_class_id,
                EnrollmentModel.deleted.is_(False),
            )
        )
        enrollment_rows = (await self.session.execute(enrollments_stmt)).all()

        records_stmt = (
            select(AttendanceRecordModel)
            .where(AttendanceRecordModel.session_id.in_(session_ids))
        )
        all_records = (await self.session.execute(records_stmt)).scalars().all()
        records_by_member: dict[UUID, list[AttendanceRecordModel]] = {}
        for record in all_records:
            records_by_member.setdefault(record.tenant_member_id, []).append(record)

        room = await self._get_class_room(subject_class_id)

        result: list[StudentAttendanceData] = []
        for enrollment, member, user in enrollment_rows:
            member_records = records_by_member.get(member.id, [])
            confirmations = [
                RawConfirmation(
                    latitude=self._extract_lat(r.student_location),
                    longitude=self._extract_lon(r.student_location),
                    record_status=r.record_status.value,
                )
                for r in member_records
            ]
            result.append(
                StudentAttendanceData(
                    tenant_member_id=member.id,
                    student_name=user.name,
                    total_sessions=total_sessions,
                    confirmations=confirmations,
                    room_lat=room.lat if room else 0.0,
                    room_lon=room.lon if room else 0.0,
                    tolerance_radius_meters=room.tolerance_radius_meters if room else 50.0,
                )
            )
        return result

    # _get_class_room, _extract_lat, _extract_lon: usam GeoAlchemy2 (to_shape),
    # seguindo o mesmo padrão já usado em record_sqlalchemy_repository.py
```

---

## Parte 5 — Persistência do Log de Execução

### 5.1 Model SQLAlchemy

```python
# src/infra/database/models/report_generation_log.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infra.database.base import Base


class ReportGenerationLogModel(Base):
    __tablename__ = "report_generation_logs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    subject_class_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subject_classes.id", ondelete="CASCADE"), nullable=False
    )
    strategy: Mapped[str] = mapped_column(String(30), nullable=False)
    workers_used: Mapped[int] = mapped_column(Integer, nullable=False)
    items_processed: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

### 5.2 Migration

```bash
uv run alembic revision --autogenerate -m "create report_generation_logs table"
uv run alembic upgrade head
```

---

## Parte 6 — Use Case (`application/use_cases/generate_class_report.py`)

Orquestra as três fases. Só ele sabe que existe uma estratégia de paralelismo — o domínio
(`calculate_student_report`) não sabe nada sobre processos, threads ou GIL.

```python
# src/modules/report/application/use_cases/generate_class_report.py
import time
from dataclasses import dataclass
from uuid import UUID

from modules.report.domain.entities.class_report import ClassReport
from modules.report.domain.services.student_calculator import calculate_student_report
from modules.report.infra.repositories.report_data_repository import ReportDataRepository
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException
from shared.parallel.compute_strategy import ComputeStrategy

RISK_THRESHOLD = 0.75


@dataclass
class GenerateClassReportInput:
    tenant_id: UUID
    subject_class_id: UUID


class GenerateClassReportUseCase:
    def __init__(
        self,
        report_data_repo: ReportDataRepository,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
        compute_strategy: ComputeStrategy,
        log_repo,  # ReportGenerationLogRepository — persiste o log de execução
    ) -> None:
        self.report_data_repo = report_data_repo
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo
        self.compute_strategy = compute_strategy
        self.log_repo = log_repo

    async def execute(self, data: GenerateClassReportInput) -> ClassReport:
        # Validações — mesmo padrão dos demais use cases do projeto
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            data.subject_class_id, data.tenant_id
        )
        if not subject_class or getattr(subject_class, "deleted", False):
            raise ResourceNotFoundException("Turma não encontrada.")

        # FASE 1 — I/O, sequencial, uma única query
        students_data = await self.report_data_repo.load_class_data(
            data.tenant_id, data.subject_class_id
        )

        # FASE 2 — CPU, paralela (estratégia injetada)
        start = time.perf_counter()
        student_reports = self.compute_strategy.compute(students_data, calculate_student_report)
        duration_ms = (time.perf_counter() - start) * 1000

        # FASE 3 — Agregação final, sequencial
        total = len(student_reports)
        avg_freq = sum(r.frequency_rate for r in student_reports) / total if total else 0.0
        at_risk_count = sum(1 for r in student_reports if r.at_risk)

        # Registra evidência de execução — vira prova numérica automática
        await self.log_repo.create(
            tenant_id=data.tenant_id,
            subject_class_id=data.subject_class_id,
            strategy=self.compute_strategy.name,
            workers_used=self.compute_strategy.workers_used,
            items_processed=total,
            duration_ms=duration_ms,
        )

        return ClassReport(
            subject_class_id=data.subject_class_id,
            total_students=total,
            class_average_frequency=round(avg_freq, 4),
            students_at_risk=at_risk_count,
            students=sorted(student_reports, key=lambda r: r.frequency_rate),
            strategy_used=self.compute_strategy.name,
            workers_used=self.compute_strategy.workers_used,
            duration_ms=round(duration_ms, 2),
        )
```

---

## Parte 7 — Router e Configuração de Estratégia por Ambiente

### 7.1 Configuração (`settings.py` — adicionar)

```python
# src/config/settings.py (MODIFICAR)
class Settings(BaseSettings):
    # ... campos existentes sem alteração ...

    # Módulo de relatórios — estratégia de paralelismo
    report_strategy: str = "process_pool"   # "sequential" | "process_pool" | "thread_pool_numpy"
    report_max_workers: int = 0             # 0 = usar cpu_budget() automaticamente
```

> **Por que isso é uma env var e não uma constante fixa?** Permite trocar a estratégia sem
> deploy novo — essencial para o benchmark comparativo em produção (Railway) e para desligar o
> paralelismo (`sequential`) caso o plano do Railway tenha CPU muito restrita e o overhead de
> processos não compense.

### 7.2 Factory de estratégia

```python
# src/modules/report/infra/strategy_factory.py
from config.settings import settings
from shared.parallel.compute_strategy import ComputeStrategy
from shared.parallel.process_pool_strategy import ProcessPoolStrategy
from shared.parallel.sequential_strategy import SequentialStrategy
from shared.parallel.thread_pool_numpy_strategy import ThreadPoolNumpyStrategy


def get_report_compute_strategy() -> ComputeStrategy:
    workers = settings.report_max_workers or None
    match settings.report_strategy:
        case "sequential":
            return SequentialStrategy()
        case "thread_pool_numpy":
            return ThreadPoolNumpyStrategy(max_workers=workers)
        case _:
            return ProcessPoolStrategy(max_workers=workers)
```

### 7.3 Router

```python
# src/modules/report/interface/router.py
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.report.application.use_cases.generate_class_report import (
    GenerateClassReportInput,
    GenerateClassReportUseCase,
)
from modules.report.infra.strategy_factory import get_report_compute_strategy
from modules.report.interface.schemas.report_schemas import ClassReportResponse
from security.dependencies.require_role import require_role
from shared.enums.user_role import UserRole

router = APIRouter(
    prefix="/tenants/{tenant_id}/subject-classes/{subject_class_id}/reports",
    tags=["reports"],
)


@router.post(
    "/frequency",
    response_model=ClassReportResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def generate_frequency_report(
    tenant_id: UUID,
    subject_class_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ClassReportResponse:
    """Gera o relatório de frequência da turma, com métricas geoespaciais recalculadas em paralelo."""
    # ... injeção dos repositórios (mesmo padrão dos demais routers) ...
    use_case = GenerateClassReportUseCase(
        report_data_repo=...,
        subject_class_repo=...,
        tenant_repo=...,
        compute_strategy=get_report_compute_strategy(),
        log_repo=...,
    )
    report = await use_case.execute(
        GenerateClassReportInput(tenant_id=tenant_id, subject_class_id=subject_class_id)
    )
    return ClassReportResponse.model_validate(report)
```

---

## Parte 8 — Script de Benchmark (`scripts/benchmark_report.py`)

Gera um dataset **sintético** (não depende do banco) grande o suficiente para tornar o ganho de
paralelismo visível, e mede as três estratégias. Serve diretamente para o gráfico do vídeo do TCC.

```python
# scripts/benchmark_report.py
"""
Uso:
    uv run python scripts/benchmark_report.py --students 5000 --sessions 40

Gera alunos e confirmações sintéticas em memória (sem tocar no banco) e mede
o tempo da Fase 2 (cálculo) com SequentialStrategy, ProcessPoolStrategy(1,2,4,8)
e ThreadPoolNumpyStrategy(1,2,4,8). Imprime tabela e salva CSV para o gráfico.
"""
import argparse
import csv
import random
import time
from uuid import uuid4

from modules.report.domain.entities.student_attendance_data import (
    RawConfirmation,
    StudentAttendanceData,
)
from modules.report.domain.services.student_calculator import calculate_student_report
from shared.parallel.process_pool_strategy import ProcessPoolStrategy
from shared.parallel.sequential_strategy import SequentialStrategy
from shared.parallel.thread_pool_numpy_strategy import ThreadPoolNumpyStrategy

ROOM_LAT, ROOM_LON = -8.04761, -34.87701


def generate_synthetic_data(n_students: int, n_sessions: int) -> list[StudentAttendanceData]:
    data = []
    for _ in range(n_students):
        confirmations = [
            RawConfirmation(
                latitude=ROOM_LAT + random.uniform(-0.0015, 0.0015),
                longitude=ROOM_LON + random.uniform(-0.0015, 0.0015),
                record_status=random.choice(["regular", "regular", "regular", "irregular"]),
            )
            for _ in range(random.randint(int(n_sessions * 0.5), n_sessions))
        ]
        data.append(
            StudentAttendanceData(
                tenant_member_id=uuid4(),
                student_name="Synthetic Student",
                total_sessions=n_sessions,
                confirmations=confirmations,
                room_lat=ROOM_LAT,
                room_lon=ROOM_LON,
                tolerance_radius_meters=50.0,
            )
        )
    return data


def run_benchmark(n_students: int, n_sessions: int) -> None:
    dataset = generate_synthetic_data(n_students, n_sessions)
    results = []

    strategies = [SequentialStrategy()]
    for n in (2, 4, 8):
        strategies.append(ProcessPoolStrategy(max_workers=n))
    for n in (2, 4, 8):
        strategies.append(ThreadPoolNumpyStrategy(max_workers=n))

    for strategy in strategies:
        start = time.perf_counter()
        strategy.compute(dataset, calculate_student_report)
        elapsed = time.perf_counter() - start
        results.append((strategy.name, strategy.workers_used, elapsed))
        print(f"{strategy.name:20s} workers={strategy.workers_used:<3d} tempo={elapsed:.3f}s")

    with open("benchmark_report_results.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["strategy", "workers", "elapsed_seconds"])
        writer.writerows(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--students", type=int, default=5000)
    parser.add_argument("--sessions", type=int, default=40)
    args = parser.parse_args()
    run_benchmark(args.students, args.sessions)
```

> **Como usar no vídeo**: rodar localmente (não no Railway — vCPU fracionada do plano gratuito
> distorce o resultado), com `--students 5000` ou mais, e mostrar o terminal com os tempos + um
> gráfico de barras gerado a partir do CSV (`matplotlib`, fora do escopo desta task de backend).

---

## Parte 9 — Extensão Opcional: Relatório Institucional (todas as turmas)

> Esta parte é **bônus**, não obrigatória para a entrega. Documentada para caso sobre tempo.

Se o tenant tem múltiplas turmas, cada turma é **também** independente das demais. Em vez de
aninhar `ProcessPoolExecutor` dentro de `ProcessPoolExecutor` (não recomendado — processos filhos
gerando processos filhos é frágil e não escala bem em Python), a abordagem correta é **achatar o
trabalho**: uma lista única de `StudentAttendanceData` de todas as turmas do tenant, processada de
uma vez pela mesma estratégia.

```python
# Errado (paralelismo aninhado):
#   for turma in turmas:
#       ProcessPoolExecutor(...).map(...)   # cria um pool POR turma — ineficiente e arriscado

# Correto (achatado):
all_students_data = []
for turma in turmas:
    all_students_data.extend(await report_data_repo.load_class_data(tenant_id, turma.id))

# Um único pool para o tenant inteiro
resultados = compute_strategy.compute(all_students_data, calculate_student_report)
```

---

## Testes

### Estratégia geral

1. **Corretude primeiro, performance depois**: todo teste de estratégia paralela deve provar que o
   resultado é **idêntico** ao da estratégia sequencial — paralelismo que muda o resultado é bug,
   não otimização.
2. Testes unitários não dependem de banco nem de rede — os processos/threads recebem apenas
   dataclasses em memória.
3. Testes de integração validam a query real do `ReportDataRepository` contra o Postgres de teste.
4. Testes E2E validam o contrato HTTP do endpoint.
5. O benchmark (Parte 8) **não é** um teste automatizado de CI — é um script manual, executado
   sob demanda para gerar evidência do vídeo. Não deve rodar em `pytest` (levaria minutos).

### 9.1 `tests/unit/shared/parallel/test_process_pool_strategy.py`

```python
from shared.parallel.process_pool_strategy import ProcessPoolStrategy
from shared.parallel.sequential_strategy import SequentialStrategy


def dobra(x: int) -> int:
    """Função de módulo — obrigatório para ser picklable pelo multiprocessing."""
    return x * 2


def test_process_pool_produz_mesmo_resultado_que_sequencial():
    items = list(range(50))
    seq_result = SequentialStrategy().compute(items, dobra)
    par_result = ProcessPoolStrategy(max_workers=4).compute(items, dobra)
    assert seq_result == par_result


def test_process_pool_com_lista_vazia_nao_falha():
    assert ProcessPoolStrategy(max_workers=4).compute([], dobra) == []


def test_process_pool_reporta_workers_usados():
    strategy = ProcessPoolStrategy(max_workers=4)
    assert strategy.workers_used == 4
    assert strategy.name == "process_pool"
```

### 9.2 `tests/unit/shared/parallel/test_thread_pool_numpy_strategy.py`

```python
import numpy as np
from shared.parallel.thread_pool_numpy_strategy import ThreadPoolNumpyStrategy


def calculo_numpy(x: np.ndarray) -> float:
    """Simula uma função que libera o GIL via NumPy."""
    return float(np.sum(np.sin(x) ** 2))


def test_thread_pool_produz_resultado_correto():
    items = [np.linspace(0, 3.14, 1000) for _ in range(20)]
    resultado = ThreadPoolNumpyStrategy(max_workers=4).compute(items, calculo_numpy)
    esperado = [calculo_numpy(x) for x in items]
    assert resultado == esperado
```

### 9.3 `tests/unit/modules/report/test_geo_metrics.py`

```python
from modules.report.domain.services.geo_metrics import (
    haversine_distance,
    haversine_distance_vectorized,
)
import numpy as np


def test_haversine_distancia_zero_no_mesmo_ponto():
    assert haversine_distance(-8.05, -34.87, -8.05, -34.87) == 0.0


def test_haversine_distancia_conhecida_aproximada():
    # Recife -> Olinda, ~6km, tolerância de 500m para variação de precisão do teste
    d = haversine_distance(-8.0476, -34.8770, -7.9997, -34.8552)
    assert 5_000 < d < 7_000


def test_versao_vetorizada_bate_com_versao_pura():
    lats = np.array([-8.0476, -8.05, -8.06])
    lons = np.array([-34.8770, -34.88, -34.89])
    vetor = haversine_distance_vectorized(lats, lons, -8.05, -34.88)
    puro = [haversine_distance(lat, lon, -8.05, -34.88) for lat, lon in zip(lats, lons)]
    assert np.allclose(vetor, puro, atol=0.01)
```

### 9.4 `tests/unit/modules/report/test_generate_class_report_use_case.py`

```python
async def test_relatorio_calcula_frequencia_correta():
    """Aluno com 8 de 10 sessões presentes -> frequency_rate = 0.8."""

async def test_relatorio_marca_at_risk_abaixo_do_limite():
    """Aluno com frequência < 75% deve ter at_risk=True."""

async def test_relatorio_registra_log_de_execucao():
    """Após gerar o relatório, deve existir 1 registro em report_generation_logs
    com strategy, workers_used e duration_ms preenchidos."""

async def test_relatorio_falha_404_se_turma_nao_encontrada():
    """Turma inexistente ou deletada -> ResourceNotFoundException."""

async def test_resultado_e_identico_entre_estrategias():
    """Gerar o mesmo relatório com SequentialStrategy e ProcessPoolStrategy
    deve produzir StudentReport idênticos (exceto metadados de execução)."""
```

### 9.5 `tests/integration/modules/report/test_report_data_repository.py`

```python
async def test_load_class_data_agrupa_confirmacoes_por_aluno():
    """Popula sessões/registros reais no banco de teste e verifica que
    StudentAttendanceData.confirmations contém exatamente os registros do aluno."""

async def test_load_class_data_aluno_sem_confirmacoes_retorna_lista_vazia():
    """Aluno matriculado que nunca confirmou presença aparece com confirmations=[]."""
```

### 9.6 `tests/e2e/modules/report/test_report_router.py`

```python
async def test_gerar_relatorio_e2e(client, session):
    """POST /reports/frequency retorna 200 com estrutura completa do relatório."""

async def test_gerar_relatorio_403_para_aluno(client, session):
    """Aluno (não professor/admin) não pode gerar relatório da turma."""

async def test_gerar_relatorio_404_turma_inexistente(client, session):
    """Turma inexistente retorna 404."""
```

---

## Ordem de Implementação

```
1.  shared/parallel/compute_strategy.py
2.  shared/parallel/cpu_budget.py
3.  shared/parallel/sequential_strategy.py
4.  shared/parallel/process_pool_strategy.py
5.  shared/parallel/thread_pool_numpy_strategy.py
6.  modules/report/domain/services/geo_metrics.py
7.  modules/report/domain/entities/student_attendance_data.py
8.  modules/report/domain/entities/student_report.py
9.  modules/report/domain/entities/class_report.py
10. modules/report/domain/services/student_calculator.py
11. infra/database/models/report_generation_log.py
12. alembic/versions/XXX_create_report_generation_logs.py
13. modules/report/infra/repositories/report_data_repository.py
14. modules/report/infra/repositories/report_generation_log_repository.py
15. modules/report/infra/strategy_factory.py
16. modules/report/application/use_cases/generate_class_report.py
17. modules/report/application/use_cases/get_student_report.py
18. modules/report/interface/schemas/report_schemas.py
19. modules/report/interface/router.py
20. config/settings.py (report_strategy, report_max_workers)
21. src/main.py (registrar router)
22. scripts/benchmark_report.py
23. tests/unit/shared/parallel/*
24. tests/unit/modules/report/*
25. tests/integration/modules/report/*
26. tests/e2e/modules/report/*
```

---

## Checklist de Implementação

- [ ] `shared/parallel/compute_strategy.py` (Protocol)
- [ ] `shared/parallel/cpu_budget.py` (respeitando `sched_getaffinity`/cgroups)
- [ ] `shared/parallel/sequential_strategy.py`
- [ ] `shared/parallel/process_pool_strategy.py`
- [ ] `shared/parallel/thread_pool_numpy_strategy.py`
- [ ] `modules/report/domain/services/geo_metrics.py` (versão pura + versão NumPy vetorizada)
- [ ] `modules/report/domain/entities/` (StudentAttendanceData, StudentReport, ClassReport)
- [ ] `modules/report/domain/services/student_calculator.py` (função-alvo do paralelismo)
- [ ] `infra/database/models/report_generation_log.py`
- [ ] Migration `report_generation_logs`
- [ ] `modules/report/infra/repositories/report_data_repository.py` (uma única query)
- [ ] `modules/report/infra/repositories/report_generation_log_repository.py`
- [ ] `modules/report/infra/strategy_factory.py` (lê `settings.report_strategy`)
- [ ] `modules/report/application/use_cases/generate_class_report.py`
- [ ] `modules/report/application/use_cases/get_student_report.py`
- [ ] `modules/report/interface/schemas/report_schemas.py`
- [ ] `modules/report/interface/router.py` (2 endpoints)
- [ ] `config/settings.py` — `report_strategy`, `report_max_workers`
- [ ] Registrar router em `main.py`
- [ ] `scripts/benchmark_report.py` (dataset sintético + CSV de saída)
- [ ] Testes unitários das 3 estratégias (equivalência de resultado sequencial vs. paralelo)
- [ ] Testes unitários de `geo_metrics` (versão pura vs. vetorizada — mesmo resultado)
- [ ] Testes unitários do use case (frequência, at_risk, log de execução, 404)
- [ ] Testes de integração do `ReportDataRepository`
- [ ] Testes E2E do router (200, 403, 404)
- [ ] Rodar `scripts/benchmark_report.py` localmente com dataset grande e documentar os números
      (tempo sequencial vs. 2/4/8 processos vs. 2/4/8 threads) para o vídeo do TCC
