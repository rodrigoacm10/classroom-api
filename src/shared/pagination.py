"""
Contrato compartilhado de paginação por offset.

Não está em uso no momento, mas será usado no futuro para paginação das
listagens que crescerem sem limite (ex.: sessões de chamada). Até lá, as
rotas continuam devolvendo lista completa.

A query, os filtros e a ordenação permanecem em cada repositório; este
módulo só descreve página, recorte e envelope da resposta.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class PaginationParams:
    """Parâmetros de offset. Ainda sem consumidores; será usado nas listagens paginadas."""

    page: int = DEFAULT_PAGE
    page_size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page deve ser maior ou igual a 1.")
        if self.page_size < 1 or self.page_size > MAX_PAGE_SIZE:
            raise ValueError(
                f"page_size deve estar entre 1 e {MAX_PAGE_SIZE}."
            )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass(frozen=True, slots=True)
class Page[T]:
    """Página de resultados no domínio. Ainda sem consumidores; será o retorno dos use cases paginados."""

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        if self.page_size <= 0 or self.total <= 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size

    @classmethod
    def from_params(
        cls, items: list[T], total: int, pagination: PaginationParams
    ) -> Page[T]:
        return cls(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )


class PageResponse[T](BaseModel):
    """Envelope HTTP da página. Ainda sem consumidores; será o response_model das rotas paginadas."""

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def of(cls, page: Page[Any], items: list[T]) -> PageResponse[T]:
        return cls(
            items=items,
            total=page.total,
            page=page.page,
            page_size=page.page_size,
            pages=page.pages,
        )


def paginate_list[T](items: Sequence[T], pagination: PaginationParams) -> Page[T]:
    """Recorta uma sequência já carregada. Útil em fakes de teste quando a rota passar a paginar."""
    sliced = list(items[pagination.offset : pagination.offset + pagination.page_size])
    return Page.from_params(sliced, total=len(items), pagination=pagination)


def get_pagination_params(
    page: Annotated[
        int,
        Query(ge=1, description="Número da página (a partir de 1)"),
    ] = DEFAULT_PAGE,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_PAGE_SIZE,
            description=f"Itens por página (máximo {MAX_PAGE_SIZE})",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> PaginationParams:
    """Depends do FastAPI para `?page=&page_size=`. Ainda não ligado a nenhuma rota."""
    return PaginationParams(page=page, page_size=page_size)
