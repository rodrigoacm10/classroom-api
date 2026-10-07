import logging
import multiprocessing as mp
import threading
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable

from shared.parallel.cpu_budget import cpu_budget

logger = logging.getLogger(__name__)

# Estado herdado pelos workers via copy-on-write do fork (Linux)
# e/ou inicializado via initializer do ProcessPoolExecutor (spawn/forkserver).
_WORKER_ITEMS: list[Any] | None = None
_WORKER_FN: Callable[[Any], Any] | None = None
_WORKER_LOCK = threading.Lock()


def _init_worker(items: list[Any], fn: Callable[[Any], Any]) -> None:
    """Inicializador de worker executado na inicialização de cada processo worker."""
    global _WORKER_ITEMS, _WORKER_FN
    _WORKER_ITEMS = items
    _WORKER_FN = fn


def _apply_item_at(index: int) -> Any:
    """Função de módulo picklable: aplica fn ao item herdado pelo fork ou initializer."""
    if _WORKER_FN is None or _WORKER_ITEMS is None:
        raise RuntimeError("Worker state is not initialized.")
    return _WORKER_FN(_WORKER_ITEMS[index])


class ProcessPoolStrategy:
    """
    Divide o trabalho entre múltiplos processos do sistema operacional.
    Cada processo tem seu próprio interpretador Python e seu próprio GIL,
    portanto o SO efetivamente escalona os processos em núcleos distintos.

    Requisitos para `fn` e para cada item de `items`:
      - `fn` deve ser uma função de módulo (não lambda, não método de instância)
        para ser "picklable".
      - Cada item deve conter apenas dados simples (dataclass com tipos
        primitivos), nunca uma conexão de banco ou sessão SQLAlchemy.
    """

    def __init__(self, max_workers: int | None = None) -> None:
        self._max_workers = max_workers or cpu_budget()

    def compute(self, items: list, fn) -> list:
        if not items:
            return []
        global _WORKER_ITEMS, _WORKER_FN
        with _WORKER_LOCK:
            _WORKER_ITEMS = items
            _WORKER_FN = fn
            try:
                mp_context = (
                    mp.get_context("fork")
                    if "fork" in mp.get_all_start_methods()
                    else mp.get_context()
                )
                with ProcessPoolExecutor(
                    max_workers=self._max_workers,
                    mp_context=mp_context,
                    initializer=_init_worker,
                    initargs=(items, fn),
                ) as pool:
                    return list(pool.map(_apply_item_at, range(len(items))))
            except Exception as exc:
                logger.warning(
                    "ProcessPoolExecutor falhou (%s). Executando cálculo sequencialmente.",
                    exc,
                )
                return [fn(item) for item in items]
            finally:
                _WORKER_ITEMS = None
                _WORKER_FN = None

    @property
    def name(self) -> str:
        return "process_pool"

    @property
    def workers_used(self) -> int:
        return self._max_workers
