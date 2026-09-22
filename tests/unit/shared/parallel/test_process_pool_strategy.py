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
