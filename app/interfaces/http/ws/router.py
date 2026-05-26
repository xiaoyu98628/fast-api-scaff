from fastapi import APIRouter

from app.interfaces.http.ws.v1.router import ws_v1_router

ws_router = APIRouter(prefix="/ws")

ws_router.include_router(ws_v1_router)
