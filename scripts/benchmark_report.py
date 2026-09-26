"""
Uso:
    uv run python scripts/benchmark_report.py --students 5000 --sessions 40 --intensity 40

Gera alunos e confirmações sintéticas em memória (sem tocar no banco) e mede
o tempo da Fase 2 (cálculo) com SequentialStrategy, ProcessPoolStrategy(2,4,8)
e ThreadPoolNumpyStrategy(2,4,8). Imprime tabela e salva CSV para o gráfico.

`--intensity` repete o cálculo por aluno sem alterar o resultado. Um semestre
real (dezenas de Haversine) é leve demais frente ao custo de criar processos;
a repetição faz o trabalho de CPU dominar, que é o que o gráfico do TCC precisa
mostrar.
"""
import argparse
import csv
import random
import sys
import time
from pathlib import Path
from uuid import uuid4

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from modules.report.domain.entities.student_attendance_data import (  # noqa: E402
    RawConfirmation,
    StudentAttendanceData,
)
from modules.report.domain.services.student_calculator import (  # noqa: E402
    calculate_student_report,
    calculate_student_report_numpy,
)
from shared.parallel.compute_strategy import ComputeStrategy  # noqa: E402
from shared.parallel.process_pool_strategy import ProcessPoolStrategy  # noqa: E402
from shared.parallel.sequential_strategy import SequentialStrategy  # noqa: E402
from shared.parallel.thread_pool_numpy_strategy import ThreadPoolNumpyStrategy  # noqa: E402

ROOM_LAT, ROOM_LON = -8.04761, -34.87701

# Lido pelos workers via fork copy-on-write; deve ser função de módulo (picklable).
INTENSITY = 1


def _bench_pure(data: StudentAttendanceData):
    result = calculate_student_report(data)
    for _ in range(INTENSITY - 1):
        result = calculate_student_report(data)
    return result


def _bench_numpy(data: StudentAttendanceData):
    result = calculate_student_report_numpy(data)
    for _ in range(INTENSITY - 1):
        result = calculate_student_report_numpy(data)
    return result


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


def run_benchmark(n_students: int, n_sessions: int, intensity: int) -> None:
    global INTENSITY
    INTENSITY = max(1, intensity)
    dataset = generate_synthetic_data(n_students, n_sessions)
    results = []

    strategies: list[ComputeStrategy] = [SequentialStrategy()]
    for n in (2, 4, 8):
        strategies.append(ProcessPoolStrategy(max_workers=n))
    for n in (2, 4, 8):
        strategies.append(ThreadPoolNumpyStrategy(max_workers=n))

    print(
        f"dataset: {n_students} alunos × ~{n_sessions} sessões × intensity={INTENSITY}\n"
    )

    for strategy in strategies:
        compute_fn = _bench_numpy if strategy.name == "thread_pool_numpy" else _bench_pure
        start = time.perf_counter()
        strategy.compute(dataset, compute_fn)
        elapsed = time.perf_counter() - start
        results.append((strategy.name, strategy.workers_used, elapsed))
        print(f"{strategy.name:20s} workers={strategy.workers_used:<3d} tempo={elapsed:.3f}s")

    output_path = Path("benchmark_report_results.csv")
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["strategy", "workers", "elapsed_seconds"])
        writer.writerows(results)
    print(f"\nResultados salvos em {output_path.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--students", type=int, default=5000)
    parser.add_argument("--sessions", type=int, default=40)
    parser.add_argument("--intensity", type=int, default=40)
    args = parser.parse_args()
    run_benchmark(args.students, args.sessions, args.intensity)
