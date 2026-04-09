"""示例与健康检查类接口：演示 API → Application → Infrastructure 调用链。"""

from fastapi import APIRouter, Depends
from starlette.requests import Request

from app.application.health.service import SystemHealthService
from app.common.response.json import JsonResponse

router = APIRouter(prefix="/test", tags=["test"])


def get_system_health_service() -> SystemHealthService:
    """FastAPI 依赖注入：无状态服务可直接 new；有状态可改为工厂或单例。"""
    return SystemHealthService()


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
    service: SystemHealthService = Depends(get_system_health_service),
) -> JsonResponse[dict[str, str | int]]:
    value = await service.db_select_one()
    return JsonResponse.success(
        data={"db": "ok", "result": value},
        message="ok",
        trace_id=getattr(request.state, "trace_id", None),
    )


@router.get(path="/redis-health", summary="Redis 连通性检测")
async def redis_health(
    request: Request,
    service: SystemHealthService = Depends(get_system_health_service),
) -> JsonResponse[dict[str, bool]]:
    ok = await service.redis_ping()
    return JsonResponse.success(
        data={"redis": ok},
        message="ok",
        trace_id=getattr(request.state, "trace_id", None),
    )
