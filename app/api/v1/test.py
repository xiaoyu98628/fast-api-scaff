from fastapi import APIRouter
from starlette.requests import Request

router = APIRouter(prefix="/test", tags=["test"])

@router.get(path="/health", summary="测试接口")
async def health(request: Request):
    """
    测试接口
    """

    print(dict(request.query_params))

    return {"code": 200, "message": "ok", "data": None}