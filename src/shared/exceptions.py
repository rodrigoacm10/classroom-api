"""
Exceções de domínio da aplicação.

Estas classes não conhecem HTTP, FastAPI, nem nenhum protocolo de transporte.
O mapeamento para status codes HTTP é feito exclusivamente na camada de interface
(shared/exception_handlers.py), mantendo os Use Cases limpos.
"""


class DomainException(Exception):
    """Base para todas as exceções originadas na camada de domínio/aplicação."""


class ResourceNotFoundException(DomainException):
    """Lançada quando um recurso obrigatório não é encontrado."""


class ResourceAlreadyExistsException(DomainException):
    """Lançada quando há tentativa de criar um recurso que já existe (conflito)."""


class BusinessRuleException(DomainException):
    """Lançada quando uma regra de negócio é violada (equivalente a 400 Bad Request)."""


class ForbiddenException(DomainException):
    """Lançada quando o usuário não tem permissão para executar a operação."""


class PlanLimitExceededException(DomainException):
    """Lançada quando o uso ultrapassa os limites do plano contratado."""

    def __init__(self, resource: str, limit: int, plan: str) -> None:
        self.resource = resource
        self.limit = limit
        self.plan = plan
        super().__init__(
            f"Limite do plano '{plan}' excedido para o recurso '{resource}' (limite: {limit})."
        )
