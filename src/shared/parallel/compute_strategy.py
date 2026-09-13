from typing import Protocol, TypeVar

T = TypeVar("T")  # tipo do item de entrada (ex: StudentAttendanceData)
R = TypeVar("R")  # tipo do resultado (ex: StudentReport)


class ComputeStrategy(Protocol[T, R]):
    """
    Executa uma função pura sobre uma lista de itens independentes entre si,
    devolvendo a lista de resultados na mesma ordem. A implementação decide
    COMO distribuir o trabalho (sequencial, múltiplos processos, múltiplas threads).
    """

    def compute(self, items: list[T], fn) -> list[R]:
        ...

    @property
    def name(self) -> str:
        """Identificador usado no report_generation_logs (ex: 'process_pool')."""
        ...

    @property
    def workers_used(self) -> int:
        """Nº de processos/threads efetivamente usados nesta execução."""
        ...
