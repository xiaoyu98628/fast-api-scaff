from fastapi import APIRouter
from starlette.requests import Request

from app.core.response.json import JsonResponse

router = APIRouter(prefix="/test", tags=["test"])


@router.get(path="/health", summary="测试接口")
async def health(request: Request) -> JsonResponse[dict[str, dict[str, str]]]:
    return JsonResponse.success(
        data={"query_params": dict(request.query_params)},
        message="ok",
        trace_id=getattr(request.state, "trace_id", None),
    )
