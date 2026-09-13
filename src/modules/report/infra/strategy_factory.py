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
