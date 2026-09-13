import numpy as np

from shared.parallel.sequential_strategy import SequentialStrategy
from shared.parallel.thread_pool_numpy_strategy import ThreadPoolNumpyStrategy


def calculo_numpy(x: np.ndarray) -> float:
    """Simula uma função que libera o GIL via NumPy."""
    return float(np.sum(np.sin(x) ** 2))


def test_thread_pool_produz_resultado_correto():
    items = [np.linspace(0, 3.14, 1000) for _ in range(20)]
    resultado = ThreadPoolNumpyStrategy(max_workers=4).compute(items, calculo_numpy)
    esperado = [calculo_numpy(x) for x in items]
    assert resultado == esperado


def test_thread_pool_produz_mesmo_resultado_que_sequencial():
    items = [np.linspace(0, 3.14, 500) for _ in range(10)]
    seq_result = SequentialStrategy().compute(items, calculo_numpy)
    par_result = ThreadPoolNumpyStrategy(max_workers=4).compute(items, calculo_numpy)
    assert seq_result == par_result


def test_thread_pool_com_lista_vazia_nao_falha():
    assert ThreadPoolNumpyStrategy(max_workers=4).compute([], calculo_numpy) == []


def test_thread_pool_reporta_workers_usados():
    strategy = ThreadPoolNumpyStrategy(max_workers=4)
    assert strategy.workers_used == 4
    assert strategy.name == "thread_pool_numpy"
