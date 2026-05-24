from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PageResult[T]:
    """应用层分页结果（对应 ai-service LengthAwarePaginator）。"""

    items: list[T]
    total: int
    page: int
    page_size: int

    @classmethod
    def empty(cls, *, page: int, page_size: int) -> PageResult[T]:
        """空分页（对应 emptyPaginator）。"""
        return cls(items=[], total=0, page=page, page_size=page_size)
