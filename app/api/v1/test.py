from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.response.json import JsonResponse
from app.infrastructure.db import get_db_session

router = APIRouter(prefix="/test", tags=["test"])


@router.get(path="/health", summary="测试接口")
async def health(request: Request) -> JsonResponse[dict[str, dict[str, str]]]:
    return JsonResponse.success(
        data={"query_params": dict(request.query_params)},
        message="ok",
        trace_id=getattr(request.state, "trace_id", None),
    )


@router.get(path="/db-health", summary="数据库连通性检测")
async def db_health(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> JsonResponse[dict[str, str | int]]:
    result = await session.execute(text("SELECT 1 AS ok"))
    row = result.mappings().one()
    return JsonResponse.success(
        data={"db": "ok", "result": row["ok"]},
        message="ok",
        trace_id=getattr(request.state, "trace_id", None),
    )
