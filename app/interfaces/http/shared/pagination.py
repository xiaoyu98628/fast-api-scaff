from collections.abc import Callable, Iterable

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PAGE = 1
DEFAULT_LIMIT = 20
MAX_LIMIT = 1000


class PageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=DEFAULT_PAGE, ge=1)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class PageMeta(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int


class PageResponse[T](BaseModel):
    items: list[T]
    meta: PageMeta


def build_page_response[S, T](
    *,
    items: Iterable[S],
    total: int,
    pagination: PageParams,
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


def calculate_total_pages(*, total: int, limit: int) -> int:
    return (total + limit - 1) // limit
