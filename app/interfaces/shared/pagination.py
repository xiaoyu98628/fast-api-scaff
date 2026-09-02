from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PageInput:
    page: int
    limit: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


@dataclass(frozen=True, slots=True)
class PageOutput[T]:
    items: tuple[T, ...]
    total: int
    page: int
    limit: int
