from concurrent.futures import ThreadPoolExecutor

from shared.parallel.cpu_budget import cpu_budget


class ThreadPoolNumpyStrategy:
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
