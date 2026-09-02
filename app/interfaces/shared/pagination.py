from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PageInput:
    page: int
    limit: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


@dataclass(frozen=True, slots=True)
class PageMeta:
    page: int
    limit: int
    total: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class PageOutput[T]:
    items: tuple[T, ...]
    meta: PageMeta


def calculate_total_pages(*, total: int, limit: int) -> int:
    return (total + limit - 1) // limit
