class SequentialStrategy:
    """Baseline sem paralelismo — usada para medir o ganho das outras estratégias."""

    def compute(self, items: list, fn) -> list:
        return [fn(item) for item in items]

    @property
    def name(self) -> str:
        return "sequential"

    @property
    def workers_used(self) -> int:
        return 1
