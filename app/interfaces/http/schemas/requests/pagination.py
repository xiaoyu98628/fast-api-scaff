from pydantic import BaseModel, Field

PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100


class PaginationQuery(BaseModel):
    """列表分页查询基类（与 ai-service meta 契约对齐）。"""

    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(
        default=PAGE_SIZE_DEFAULT,
        ge=1,
        le=PAGE_SIZE_MAX,
        description="每页条数，上限 100",
    )
