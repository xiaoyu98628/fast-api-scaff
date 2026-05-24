from collections.abc import Callable

from app.application.support.pagination import PageResult
from app.interfaces.http.schemas.responses.pagination import PaginatedData, paginated


def to_paginated[T, R](page: PageResult[T], mapper: Callable[[T], R]) -> PaginatedData[R]:
    """将 PageResult 转为对外分页响应（对应 BaseCollection + Resource）。"""
    return paginated(
        [mapper(item) for item in page.items],
        total=page.total,
        page=page.page,
        page_size=page.page_size,
    )
