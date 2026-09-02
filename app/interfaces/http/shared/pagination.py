from pydantic import BaseModel, ConfigDict, Field

from app.interfaces.shared.pagination import PageInput

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
    total: int
    page: int
    limit: int
