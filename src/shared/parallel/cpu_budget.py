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
