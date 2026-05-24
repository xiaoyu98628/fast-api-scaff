from pydantic import BaseModel, Field


class PageMeta(BaseModel):
    """分页元信息（字段与 ai-service BaseCollection 一致）。"""

    current_page: int = Field(ge=1, description="当前页码")
    last_page: int = Field(ge=1, description="最后一页页码")
    total: int = Field(ge=0, description="总记录数")
    page_size: int = Field(ge=1, le=100, description="每页条数，上限 100")


class PaginatedData[T](BaseModel):
    """分页列表数据结构：data + meta。"""

    data: list[T]
    meta: PageMeta


def build_page_meta(*, total: int, page: int, page_size: int) -> PageMeta:
    """根据分页参数构建 meta。"""
    if total == 0:
        last_page = 1
    else:
        last_page = (total + page_size - 1) // page_size

    return PageMeta(
        current_page=page,
        last_page=last_page,
        total=total,
        page_size=page_size,
    )


def paginated[T](
    items: list[T],
    *,
    total: int,
    page: int,
    page_size: int,
) -> PaginatedData[T]:
    """封装分页列表响应体。"""
    return PaginatedData(
        data=items,
        meta=build_page_meta(total=total, page=page, page_size=page_size),
    )
