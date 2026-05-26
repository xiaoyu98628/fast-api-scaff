from fastapi import APIRouter

ws_v1_router = APIRouter(prefix="/v1")

# WebSocket endpoints：在 ws/v1/endpoints/ 增加模块后于此挂载。
