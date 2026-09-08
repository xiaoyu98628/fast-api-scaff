"""定义 HTTP 列表接口共用的分页参数与响应结构。"""

from collections.abc import Callable, Iterable

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PAGE = 1
DEFAULT_LIMIT = 20
MAX_LIMIT = 1000


class PageParams(BaseModel):
    """校验从 1 开始的页码和单页数量。"""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=DEFAULT_PAGE, ge=1)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)

    @property
    def offset(self) -> int:
        """把页码转换为仓储查询使用的零基偏移量。"""

        return (self.page - 1) * self.limit


class PageMeta(BaseModel):
    """描述当前分页窗口和完整结果规模。"""

    page: int
    limit: int
    total: int
    total_pages: int


class PageResponse[T](BaseModel):
    """封装映射后的列表项和分页元数据。"""

    items: list[T]
    meta: PageMeta


def build_page_response[S, T](
    *,
    items: Iterable[S],
    total: int,
    pagination: PageParams,
    item_mapper: Callable[[S], T],
) -> PageResponse[T]:
    """映射应用层结果并组装 HTTP 分页响应。"""

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
    """使用整数运算向上取整总页数。"""

    return (total + limit - 1) // limit
