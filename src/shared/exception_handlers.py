"""
Handlers globais que mapeiam exceções de domínio para respostas HTTP.

Este é o ÚNICO lugar da aplicação onde exceções de domínio ganham
conhecimento de HTTP (status code, formato de body). Os Use Cases
continuam completamente agnósticos ao protocolo.

Registre todos os handlers em main.py via app.add_exception_handler().
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse

from shared.exceptions import (
    BusinessRuleException,
    DomainException,
    ForbiddenException,
    PlanLimitExceededException,
    ResourceAlreadyExistsException,
    ResourceNotFoundException,
)


async def resource_not_found_handler(
    request: Request, exc: ResourceNotFoundException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


async def resource_already_exists_handler(
    request: Request, exc: ResourceAlreadyExistsException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


async def business_rule_handler(
    request: Request, exc: BusinessRuleException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


async def forbidden_handler(
    request: Request, exc: ForbiddenException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc)},
    )


async def plan_limit_exceeded_handler(
    request: Request, exc: PlanLimitExceededException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "code": "PLAN_LIMIT_EXCEEDED",
            "resource": exc.resource,
            "limit": exc.limit,
            "plan": exc.plan,
            "detail": str(exc),
        },
    )


async def generic_domain_exception_handler(
    request: Request, exc: DomainException
) -> JSONResponse:
    """Fallback para exceções de domínio não tratadas especificamente."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc)},
    )


def register_exception_handlers(app: object) -> None:
    """
    Registra todos os handlers de exceções de domínio na instância do FastAPI.

    Uso em main.py:
        from shared.exception_handlers import register_exception_handlers
        register_exception_handlers(app)
    """
    # Handlers específicos devem ser registrados ANTES do handler genérico
    app.add_exception_handler(ResourceNotFoundException, resource_not_found_handler)
    app.add_exception_handler(ResourceAlreadyExistsException, resource_already_exists_handler)
    app.add_exception_handler(BusinessRuleException, business_rule_handler)
    app.add_exception_handler(ForbiddenException, forbidden_handler)
    app.add_exception_handler(PlanLimitExceededException, plan_limit_exceeded_handler)
    # Fallback genérico para DomainException base (deve ser o último)
    app.add_exception_handler(DomainException, generic_domain_exception_handler)
