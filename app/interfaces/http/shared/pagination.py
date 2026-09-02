from collections.abc import Callable, Iterable

from pydantic import BaseModel, ConfigDict, Field

from app.interfaces.shared.pagination import PageInput, PageMeta, calculate_total_pages

DEFAULT_PAGE = 1
DEFAULT_LIMIT = 20
MAX_LIMIT = 1000


class PageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=DEFAULT_PAGE, ge=1)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)

    def to_input(self) -> PageInput:
        return PageInput(page=self.page, limit=self.limit)


class PageResponse[T](BaseModel):
    items: list[T]
    meta: PageMeta


def build_page_response[S, T](
    *,
    items: Iterable[S],
    total: int,
    pagination: PageInput,
    item_mapper: Callable[[S], T],
) -> PageResponse[T]:
    mapped_items: list[T] = [item_mapper(item) for item in items]

    return PageResponse(
        items=mapped_items,
        meta=PageMeta(
            page=pagination.page,
            limit=pagination.limit,
            total=total,
            total_pages=calculate_total_pages(
                total=total,
                limit=pagination.limit,
            ),
        ),
    )
