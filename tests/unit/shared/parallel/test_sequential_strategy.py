from shared.parallel.cpu_budget import cpu_budget
from shared.parallel.sequential_strategy import SequentialStrategy


def dobra(x: int) -> int:
    return x * 2


def test_sequential_produz_resultado_na_mesma_ordem():
    items = list(range(10))
    result = SequentialStrategy().compute(items, dobra)
    assert result == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]


def test_sequential_com_lista_vazia_nao_falha():
    assert SequentialStrategy().compute([], dobra) == []


def test_sequential_reporta_workers_usados():
    strategy = SequentialStrategy()
    assert strategy.workers_used == 1
    assert strategy.name == "sequential"


def test_cpu_budget_retorna_pelo_menos_um_nucleo():
    assert cpu_budget() >= 1
