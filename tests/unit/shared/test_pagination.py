import pytest
from pydantic import BaseModel

from shared.pagination import (
    MAX_PAGE_SIZE,
    Page,
    PageResponse,
    PaginationParams,
    get_pagination_params,
    paginate_list,
)


class TestPaginationParams:
    def test_defaults_and_first_page_offset(self):
        params = PaginationParams()
        assert params.page == 1
        assert params.page_size == 20
        assert params.offset == 0

    def test_offset_for_later_pages(self):
        assert PaginationParams(page=3, page_size=20).offset == 40

    def test_rejects_page_below_one(self):
        with pytest.raises(ValueError, match="page"):
            PaginationParams(page=0)

    def test_rejects_page_size_out_of_range(self):
        with pytest.raises(ValueError, match="page_size"):
            PaginationParams(page_size=0)
        with pytest.raises(ValueError, match="page_size"):
            PaginationParams(page_size=MAX_PAGE_SIZE + 1)


class TestPaginateList:
    def test_first_page(self):
        page = paginate_list(list(range(1, 8)), PaginationParams(page=1, page_size=3))
        assert page.items == [1, 2, 3]
        assert page.total == 7
        assert page.page == 1
        assert page.page_size == 3
        assert page.pages == 3

    def test_last_partial_page(self):
        page = paginate_list(list(range(1, 8)), PaginationParams(page=3, page_size=3))
        assert page.items == [7]
        assert page.total == 7
        assert page.pages == 3

    def test_page_beyond_total_is_empty(self):
        page = paginate_list(list(range(1, 4)), PaginationParams(page=5, page_size=3))
        assert page.items == []
        assert page.total == 3
        assert page.pages == 1

    def test_empty_source(self):
        page = paginate_list([], PaginationParams())
        assert page.items == []
        assert page.total == 0
        assert page.pages == 0


class ItemSchema(BaseModel):
    value: int


class TestPageResponse:
    def test_of_maps_items_and_keeps_page_metadata(self):
        domain_page = Page.from_params(
            items=["a", "b"],
            total=5,
            pagination=PaginationParams(page=2, page_size=2),
        )
        response = PageResponse.of(
            domain_page,
            items=[ItemSchema(value=1), ItemSchema(value=2)],
        )
        assert response.items == [ItemSchema(value=1), ItemSchema(value=2)]
        assert response.total == 5
        assert response.page == 2
        assert response.page_size == 2
        assert response.pages == 3


class TestGetPaginationParams:
    def test_query_defaults(self):
        params = get_pagination_params()
        assert params == PaginationParams()

    def test_query_explicit_values(self):
        params = get_pagination_params(page=2, page_size=10)
        assert params.page == 2
        assert params.page_size == 10
        assert params.offset == 10
