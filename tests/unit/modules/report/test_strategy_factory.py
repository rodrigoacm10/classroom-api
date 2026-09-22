from config.settings import settings
from modules.report.infra.strategy_factory import get_report_compute_strategy
from shared.parallel.process_pool_strategy import ProcessPoolStrategy
from shared.parallel.sequential_strategy import SequentialStrategy
from shared.parallel.thread_pool_numpy_strategy import ThreadPoolNumpyStrategy


def test_factory_retorna_sequential(monkeypatch):
    """Deve instanciar SequentialStrategy quando REPORT_STRATEGY=sequential."""
    monkeypatch.setattr(settings, "report_strategy", "sequential")
    monkeypatch.setattr(settings, "report_max_workers", 0)
    strategy = get_report_compute_strategy()
    assert isinstance(strategy, SequentialStrategy)
    assert strategy.name == "sequential"


def test_factory_retorna_thread_pool_numpy(monkeypatch):
    """Deve instanciar ThreadPoolNumpyStrategy com o nº de workers configurado."""
    monkeypatch.setattr(settings, "report_strategy", "thread_pool_numpy")
    monkeypatch.setattr(settings, "report_max_workers", 3)
    strategy = get_report_compute_strategy()
    assert isinstance(strategy, ThreadPoolNumpyStrategy)
    assert strategy.workers_used == 3


def test_factory_default_e_process_pool(monkeypatch):
    """Deve instanciar ProcessPoolStrategy quando REPORT_STRATEGY=process_pool."""
    monkeypatch.setattr(settings, "report_strategy", "process_pool")
    monkeypatch.setattr(settings, "report_max_workers", 2)
    strategy = get_report_compute_strategy()
    assert isinstance(strategy, ProcessPoolStrategy)
    assert strategy.workers_used == 2


def test_factory_valor_desconhecido_cai_em_process_pool(monkeypatch):
    """Deve usar ProcessPoolStrategy como fallback quando REPORT_STRATEGY é inválido."""
    monkeypatch.setattr(settings, "report_strategy", "cuda")
    monkeypatch.setattr(settings, "report_max_workers", 2)
    strategy = get_report_compute_strategy()
    assert isinstance(strategy, ProcessPoolStrategy)
    assert strategy.name == "process_pool"
