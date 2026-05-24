from typing import Any

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession


async def paginate(
    session: AsyncSession,
    *,
    count_stmt: Select[Any],
    data_stmt: Select[Any],
    page: int,
    page_size: int,
) -> tuple[list[Any], int]:
    """执行 count + offset/limit，返回 (rows, total)。"""
    total = int(await session.scalar(count_stmt) or 0)
    offset = (page - 1) * page_size
    result = await session.execute(data_stmt.offset(offset).limit(page_size))
    return list(result.scalars().all()), total
